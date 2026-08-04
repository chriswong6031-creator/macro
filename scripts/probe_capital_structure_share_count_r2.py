"""Run the isolated, review-only share-count R2 conformance probe.

This command is intentionally an operator boundary, not a publication lane.
It accepts no storage configuration from flags, requires only the dedicated
``R2_SHARE_COUNT_CONFORMANCE_*`` environment, supplies the core with an
exact-fresh-key capability, and writes one canonical *local* receipt for Actions
artifact review.  It never writes a receipt to R2 and never offers object
listing, deletion, publication, or signing capabilities to the core.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.util
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


RECEIPT_FILENAME = "capital_structure_share_count_r2_conformance_receipt.json"
CLI_DEADLINE_SECONDS = 90
PROCESS_ALARM_SECONDS = 95
MAX_RECEIPT_BYTES = 256 * 1024
_ACCOUNT_ID_RE = re.compile(r"^[a-f0-9]{32}$")
_ACCESS_KEY_RE = re.compile(r"^[A-Za-z0-9]{16,128}$")
_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_R2_HOST_RE = re.compile(
    r"^(?P<account_id>[a-f0-9]{32})\.(?:(?:eu|fedramp)\.)?r2\.cloudflarestorage\.com$"
)
_RANGE_RE = re.compile(r"^bytes=0-(?P<end>[0-9]{1,4})$")
_GITHUB_SHA_RE = re.compile(r"^[a-f0-9]{40}$")
_GITHUB_WORKFLOW_REF_RE = re.compile(
    r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/\.github/workflows/"
    r"capital-share-count-r2-conformance\.yml@refs/heads/main$"
)
_GITHUB_ACTOR_RE = re.compile(r"^[A-Za-z0-9-]{1,39}$")
_EXPECTED_REPOSITORY = "chriswong6031-creator/macro"
_HEX64_RE = re.compile(r"^[a-f0-9]{64}$")
_REQUIRED_ENV = (
    "R2_SHARE_COUNT_CONFORMANCE_ENDPOINT",
    "R2_SHARE_COUNT_CONFORMANCE_ACCOUNT_ID",
    "R2_SHARE_COUNT_CONFORMANCE_BUCKET",
    "R2_SHARE_COUNT_CONFORMANCE_ACCESS_KEY_ID",
    "R2_SHARE_COUNT_CONFORMANCE_SECRET_ACCESS_KEY",
)
_EXECUTION_ENV = (
    "CAPITAL_STRUCTURE_R2_CONFORMANCE_SOURCE_ARCHIVE_SHA256",
    "CAPITAL_STRUCTURE_R2_CONFORMANCE_DEPENDENCY_LOCK_SHA256",
)
_CORE_MODULE_NAME = "_capital_structure_share_count_r2_conformance_reviewed"
_CORE_PATH = (
    Path(__file__).resolve().parents[1]
    / "engine"
    / "capital_structure"
    / "share_count_r2_conformance.py"
)


class ShareCountR2ConformanceError(RuntimeError):
    """The isolated operator probe cannot safely establish conformance."""


class ConformanceDeadlineExceeded(ShareCountR2ConformanceError):
    """The fixed, short operator deadline elapsed."""

    conformance_deadline_exceeded = True


@dataclass(frozen=True)
class ConformanceR2Config:
    endpoint: str
    account_id: str
    bucket: str
    access_key_id: str
    secret_access_key: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_endpoint(*, endpoint: str, account_id: str) -> str:
    if not isinstance(account_id, str) or _ACCOUNT_ID_RE.fullmatch(account_id) is None:
        raise ShareCountR2ConformanceError("dedicated R2 account ID is invalid")
    if not isinstance(endpoint, str) or len(endpoint) > 256:
        raise ShareCountR2ConformanceError("dedicated R2 endpoint is invalid")
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError as exc:
        raise ShareCountR2ConformanceError("dedicated R2 endpoint is invalid") from exc
    host = parsed.hostname
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or host is None
        or endpoint not in {f"https://{host}", f"https://{host}/"}
    ):
        raise ShareCountR2ConformanceError("dedicated R2 endpoint is invalid")
    match = _R2_HOST_RE.fullmatch(host)
    if match is None or match.group("account_id") != account_id:
        raise ShareCountR2ConformanceError(
            "dedicated R2 endpoint does not bind the supplied account ID"
        )
    return f"https://{host}"


def read_conformance_config() -> ConformanceR2Config:
    """Load exactly the five isolated conformance secrets; no fallback exists."""
    values = {name: os.environ.get(name, "") for name in _REQUIRED_ENV}
    if any(not values[name] for name in _REQUIRED_ENV):
        raise ShareCountR2ConformanceError("dedicated share-count conformance R2 credential is unavailable")
    endpoint = _canonical_endpoint(
        endpoint=values["R2_SHARE_COUNT_CONFORMANCE_ENDPOINT"],
        account_id=values["R2_SHARE_COUNT_CONFORMANCE_ACCOUNT_ID"],
    )
    bucket = values["R2_SHARE_COUNT_CONFORMANCE_BUCKET"]
    if _BUCKET_RE.fullmatch(bucket) is None or ".." in bucket:
        raise ShareCountR2ConformanceError("dedicated R2 bucket is invalid")
    access_key_id = values["R2_SHARE_COUNT_CONFORMANCE_ACCESS_KEY_ID"]
    if _ACCESS_KEY_RE.fullmatch(access_key_id) is None:
        raise ShareCountR2ConformanceError("dedicated R2 access key ID is invalid")
    secret_access_key = values["R2_SHARE_COUNT_CONFORMANCE_SECRET_ACCESS_KEY"]
    if (
        not secret_access_key
        or len(secret_access_key.encode("utf-8")) > 512
        or any(character.isspace() for character in secret_access_key)
    ):
        raise ShareCountR2ConformanceError("dedicated R2 secret access key is invalid")
    return ConformanceR2Config(
        endpoint=endpoint,
        account_id=values["R2_SHARE_COUNT_CONFORMANCE_ACCOUNT_ID"],
        bucket=bucket,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
    )


def build_sigv4_client(config: ConformanceR2Config) -> Any:
    """Build the exact Cloudflare R2 Signature V4 client for this one probe."""
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise ShareCountR2ConformanceError(
            "boto3 is unavailable for share-count R2 conformance"
        ) from exc
    options = {
        "region_name": "auto",
        "signature_version": "s3v4",
        "max_pool_connections": 1,
        "retries": {"total_max_attempts": 1, "mode": "standard"},
        "connect_timeout": 5,
        "read_timeout": 15,
    }
    try:
        client_config = Config(
            **options,
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        )
    except TypeError:
        client_config = Config(**options)
    client = boto3.client(
        "s3",
        endpoint_url=config.endpoint,
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        config=client_config,
    )
    _preflight_r2_sdk_models(client)
    return client


def _preflight_r2_sdk_models(client: Any) -> None:
    """Reject an SDK that cannot express the exact conditional protocol."""
    try:
        service_model = client.meta.service_model
        put_members = service_model.operation_model("PutObject").input_shape.members
        get_members = service_model.operation_model("GetObject").input_shape.members
    except Exception as exc:  # noqa: BLE001 - no usable SDK model is fail-closed.
        raise ShareCountR2ConformanceError(
            "boto3 SDK cannot preflight share-count conformance operations"
        ) from exc
    if not {"IfMatch", "IfNoneMatch"}.issubset(put_members) or "IfMatch" not in get_members:
        raise ShareCountR2ConformanceError(
            "boto3 SDK lacks required conditional share-count conformance operations"
        )


class ConformanceR2ObjectClient:
    """Deliberately tiny capability adapter around a boto3 S3 client.

    The conformance core receives no general-purpose boto interface. It can
    operate on exactly its one fresh, disposable key with HEAD, GET, and the
    conditional PUT protocol preflighted above. All discovery, deletion, and
    every other target are absent by construction.
    """

    __slots__ = ("__client", "_bucket", "_key")

    def __init__(self, client: Any, *, bucket: str, key: str) -> None:
        self.__client = client
        self._bucket = bucket
        self._key = key

    def _assert_target(self, kwargs: Mapping[str, Any]) -> None:
        if kwargs.get("Bucket") != self._bucket or kwargs.get("Key") != self._key:
            raise ShareCountR2ConformanceError(
                "share-count conformance attempted an unadmitted R2 target"
            )

    @staticmethod
    def _require_opaque_condition(value: Any) -> None:
        if (
            not isinstance(value, str)
            or not value
            or len(value.encode("utf-8")) > 1024
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise ShareCountR2ConformanceError(
                "share-count conformance condition is invalid"
            )

    def head_object(self, **kwargs: Any) -> Any:
        self._assert_target(kwargs)
        if set(kwargs) != {"Bucket", "Key"}:
            raise ShareCountR2ConformanceError(
                "share-count conformance HEAD parameters are not admitted"
            )
        return self.__client.head_object(**kwargs)

    def get_object(self, **kwargs: Any) -> Any:
        self._assert_target(kwargs)
        if set(kwargs) != {"Bucket", "Key", "Range", "IfMatch"}:
            raise ShareCountR2ConformanceError(
                "share-count conformance GET parameters are not admitted"
            )
        match = _RANGE_RE.fullmatch(kwargs["Range"]) if isinstance(kwargs["Range"], str) else None
        if match is None or int(match.group("end")) >= 4096:
            raise ShareCountR2ConformanceError(
                "share-count conformance GET range is invalid"
            )
        self._require_opaque_condition(kwargs["IfMatch"])
        return self.__client.get_object(**kwargs)

    def put_object(self, **kwargs: Any) -> Any:
        self._assert_target(kwargs)
        base = {"Bucket", "Key", "Body", "ContentType"}
        conditions = {name for name in ("IfMatch", "IfNoneMatch") if name in kwargs}
        if set(kwargs) != base | conditions or len(conditions) != 1:
            raise ShareCountR2ConformanceError(
                "share-count conformance PUT parameters are not admitted"
            )
        body = kwargs["Body"]
        if (
            not isinstance(body, bytes)
            or not 1 <= len(body) <= 4096
            or kwargs["ContentType"] != "application/json"
        ):
            raise ShareCountR2ConformanceError(
                "share-count conformance PUT body is invalid"
            )
        if "IfNoneMatch" in conditions:
            if kwargs["IfNoneMatch"] != "*":
                raise ShareCountR2ConformanceError(
                    "share-count conformance IfNoneMatch condition is invalid"
                )
        else:
            self._require_opaque_condition(kwargs["IfMatch"])
        return self.__client.put_object(**kwargs)

    def __getattr__(self, name: str) -> Any:
        raise ShareCountR2ConformanceError(
            f"share-count conformance client capability is not admitted: {name}"
        )


def _require_remaining(deadline: float, *, monotonic: Any = time.monotonic) -> float:
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise ConformanceDeadlineExceeded("share-count conformance exceeded 90 seconds")
    return remaining


def github_provenance_from_environment() -> dict[str, Any]:
    """Capture the non-secret GitHub identity the core receipt must bind."""
    values = {
        "repository": os.environ.get("GITHUB_REPOSITORY", ""),
        "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF", ""),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        "commit_sha": os.environ.get("GITHUB_SHA", ""),
        "event_name": os.environ.get("GITHUB_EVENT_NAME", ""),
        "actor": os.environ.get("GITHUB_ACTOR", ""),
    }
    if (
        values["repository"] != _EXPECTED_REPOSITORY
        or _GITHUB_WORKFLOW_REF_RE.fullmatch(values["workflow_ref"]) is None
        or _GITHUB_SHA_RE.fullmatch(values["commit_sha"]) is None
        or values["event_name"] != "workflow_dispatch"
        or _GITHUB_ACTOR_RE.fullmatch(values["actor"]) is None
        or not values["run_id"].isdigit()
        or not values["run_attempt"].isdigit()
        or int(values["run_id"]) <= 0
        or int(values["run_attempt"]) <= 0
        or values["workflow_ref"] != (
            f"{values['repository']}/.github/workflows/"
            "capital-share-count-r2-conformance.yml@refs/heads/main"
        )
    ):
        raise ShareCountR2ConformanceError("GitHub conformance provenance is invalid")
    return {
        "repository": values["repository"],
        "workflow_ref": values["workflow_ref"],
        "run_id": values["run_id"],
        "run_attempt": int(values["run_attempt"]),
        "commit_sha": values["commit_sha"],
        "event_name": values["event_name"],
        "actor": values["actor"],
    }


def execution_provenance_from_environment() -> dict[str, str]:
    values = {name: os.environ.get(name, "") for name in _EXECUTION_ENV}
    if any(_HEX64_RE.fullmatch(value) is None for value in values.values()):
        raise ShareCountR2ConformanceError("reviewed execution provenance is invalid")
    return {
        "source_archive_sha256": values[
            "CAPITAL_STRUCTURE_R2_CONFORMANCE_SOURCE_ARCHIVE_SHA256"
        ],
        "dependency_lock_sha256": values[
            "CAPITAL_STRUCTURE_R2_CONFORMANCE_DEPENDENCY_LOCK_SHA256"
        ],
    }


def _load_conformance_core() -> Any:
    cached = sys.modules.get(_CORE_MODULE_NAME)
    if cached is not None:
        return cached
    try:
        spec = importlib.util.spec_from_file_location(_CORE_MODULE_NAME, _CORE_PATH)
        if spec is None or spec.loader is None:
            raise ImportError("reviewed core has no import specification")
        module = importlib.util.module_from_spec(spec)
        sys.modules[_CORE_MODULE_NAME] = module
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 - a missing reviewed core is a failed probe.
        sys.modules.pop(_CORE_MODULE_NAME, None)
        raise ShareCountR2ConformanceError("share-count conformance core is unavailable") from exc
    return module


def invoke_conformance_core(
    *,
    client: ConformanceR2ObjectClient,
    bucket: str,
    key: str,
    endpoint_host: str,
    github_provenance: Mapping[str, Any],
    execution_provenance: Mapping[str, Any],
    observed_at: datetime,
    deadline: float,
) -> Mapping[str, Any]:
    """Call the reviewed core through its fixed, capability-limited interface."""
    core = _load_conformance_core()
    runner = getattr(core, "run_conformance", None)
    if not callable(runner):
        raise ShareCountR2ConformanceError("share-count conformance core entry point is unavailable")
    result = runner(
        client=client,
        bucket=bucket,
        key=key,
        endpoint_host=endpoint_host,
        github_provenance=github_provenance,
        execution_provenance=execution_provenance,
        observed_at=observed_at,
        deadline_seconds=_require_remaining(deadline),
    )
    if not isinstance(result, Mapping):
        raise ShareCountR2ConformanceError("share-count conformance core result is invalid")
    if result.get("status") != "passed":
        raise ShareCountR2ConformanceError("share-count conformance core did not pass")
    receipt = result.get("receipt")
    if not isinstance(receipt, Mapping):
        raise ShareCountR2ConformanceError("share-count conformance receipt is invalid")
    canonicalizer = getattr(core, "canonical_receipt_bytes", None)
    if not callable(canonicalizer):
        raise ShareCountR2ConformanceError("share-count conformance receipt canonicalizer is unavailable")
    try:
        receipt_bytes = canonicalizer(receipt)
    except Exception as exc:  # noqa: BLE001 - core receipt validation is fail-closed.
        raise ShareCountR2ConformanceError("share-count conformance receipt is invalid") from exc
    if not isinstance(receipt_bytes, bytes) or len(receipt_bytes) > MAX_RECEIPT_BYTES:
        raise ShareCountR2ConformanceError("share-count conformance receipt is invalid")
    return {"core": core, "receipt": dict(receipt), "receipt_bytes": receipt_bytes}


def write_local_receipt(output_dir: str | Path, receipt: bytes) -> Path:
    """Atomically write the only receipt; this function has no R2 dependency."""
    destination = Path(output_dir)
    if destination.exists() and destination.is_symlink():
        raise ShareCountR2ConformanceError("receipt output directory cannot be a symlink")
    destination.mkdir(parents=True, exist_ok=True)
    if not destination.is_dir():
        raise ShareCountR2ConformanceError("receipt output directory is invalid")
    payload = receipt
    if not payload.endswith(b"\n") or len(payload) > MAX_RECEIPT_BYTES:
        raise ShareCountR2ConformanceError("canonical receipt payload is invalid")
    final = destination / RECEIPT_FILENAME
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".share_count_r2_conformance_", suffix=".tmp", dir=destination
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, final)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
    return final


def _deadline_handler(_signum: int, _frame: Any) -> None:
    raise ConformanceDeadlineExceeded("share-count conformance exceeded process watchdog")


def _failure_status_and_classification(
    *, phase: str, error: BaseException
) -> tuple[str, str, str]:
    """Reduce wrapper errors to the core's closed, review-safe failure codes."""
    if isinstance(error, ConformanceDeadlineExceeded):
        return "inconclusive", "probe", "deadline"
    if phase in {"provenance", "configuration", "client_initialization"}:
        return "failed", "setup", "configuration"
    if phase == "receipt_write":
        return "failed", "receipt", "configuration"
    return "inconclusive", "probe", "unknown"


def _core_failure_receipt(
    *,
    core: Any,
    phase: str,
    error: BaseException,
    bucket: str | None,
    endpoint_host: str | None,
    github_provenance: Mapping[str, Any],
    execution_provenance: Mapping[str, Any],
    observed_at: datetime,
    fresh_key: str,
) -> bytes:
    builder = getattr(core, "build_failure_receipt", None)
    canonicalizer = getattr(core, "canonical_receipt_bytes", None)
    if not callable(builder) or not callable(canonicalizer):
        raise ShareCountR2ConformanceError("share-count failure receipt helper is unavailable")
    completed_steps: tuple[str, ...] = ()
    classifier = getattr(core, "failure_receipt_evidence", None)
    if phase == "core_conformance" and callable(classifier):
        evidence = classifier(error)
        status = evidence["status"]
        stage = evidence["failure_stage"]
        category = evidence["failure_category"]
        completed_steps = tuple(evidence["completed_steps"])
    else:
        status, stage, category = _failure_status_and_classification(phase=phase, error=error)
    receipt = builder(
        status=status,
        failure_stage=stage,
        failure_category=category,
        bucket=bucket,
        key=fresh_key,
        endpoint_host=endpoint_host,
        github_provenance=github_provenance,
        execution_provenance=execution_provenance,
        observed_at=observed_at,
        deadline_seconds=CLI_DEADLINE_SECONDS,
        completed_steps=completed_steps,
    )
    payload = canonicalizer(receipt)
    if not isinstance(payload, bytes) or len(payload) > MAX_RECEIPT_BYTES:
        raise ShareCountR2ConformanceError("share-count failure receipt is invalid")
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        required=True,
        help="local review-only artifact directory; never an R2 destination",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    observed_at = _utc_now()
    fresh_key = "capital_structure/share_counts/conformance/v1/" + secrets.token_hex(16) + ".json"
    deadline = time.monotonic() + CLI_DEADLINE_SECONDS
    previous_handler = None
    timer_armed = False
    phase = "provenance"
    config: ConformanceR2Config | None = None
    endpoint_host: str | None = None
    github_provenance: Mapping[str, Any] | None = None
    execution_provenance: Mapping[str, Any] | None = None
    core_module: Any | None = None
    try:
        if hasattr(signal, "SIGALRM") and hasattr(signal, "setitimer"):
            previous_handler = signal.signal(signal.SIGALRM, _deadline_handler)
            # The core's monotonic 90-second deadline owns normal cleanup. This
            # later alarm is only a stuck-call backstop and must not race the
            # core while it transfers or closes a returned StreamingBody.
            signal.setitimer(signal.ITIMER_REAL, PROCESS_ALARM_SECONDS)
            timer_armed = True
        github_provenance = github_provenance_from_environment()
        phase = "execution_provenance"
        execution_provenance = execution_provenance_from_environment()
        phase = "configuration"
        config = read_conformance_config()
        endpoint_host = urlsplit(config.endpoint).hostname
        if endpoint_host is None:
            raise ShareCountR2ConformanceError("dedicated R2 endpoint host is invalid")
        core_module = _load_conformance_core()
        phase = "client_initialization"
        raw_client = build_sigv4_client(config)
        client = ConformanceR2ObjectClient(
            raw_client,
            bucket=config.bucket,
            key=fresh_key,
        )
        # The boto client has captured the secret. Do not leave a second copy
        # in this process environment while the reviewed core executes.
        os.environ.pop("R2_SHARE_COUNT_CONFORMANCE_ACCESS_KEY_ID", None)
        os.environ.pop("R2_SHARE_COUNT_CONFORMANCE_SECRET_ACCESS_KEY", None)
        phase = "core_conformance"
        conformance = invoke_conformance_core(
            client=client,
            bucket=config.bucket,
            key=fresh_key,
            endpoint_host=endpoint_host,
            github_provenance=github_provenance,
            execution_provenance=execution_provenance,
            observed_at=observed_at,
            deadline=deadline,
        )
        _require_remaining(deadline)
        phase = "receipt_write"
        write_local_receipt(args.output_dir, conformance["receipt_bytes"])
    except Exception as exc:  # noqa: BLE001 - always reduce failure to a safe type code.
        try:
            if core_module is None:
                core_module = _load_conformance_core()
            write_local_receipt(
                args.output_dir,
                _core_failure_receipt(
                    core=core_module,
                    phase=phase,
                    error=exc,
                    bucket=config.bucket if config is not None else None,
                    endpoint_host=endpoint_host,
                    github_provenance=github_provenance,
                    execution_provenance=execution_provenance,
                    observed_at=observed_at,
                    fresh_key=fresh_key,
                ),
            )
        except Exception:
            pass
        print(f"::error title=share_count_r2_conformance::{phase} failed", flush=True)
        return 1
    finally:
        if timer_armed:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)
    print(
        "::notice title=share_count_r2_conformance::review-only receipt is available as an artifact",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
