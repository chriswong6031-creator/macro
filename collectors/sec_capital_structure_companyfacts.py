"""Bounded SEC Company Facts evidence intake for Capital Structure Intelligence.

This is a source-plane collector, deliberately separate from the filing-document
``capital_structure.source_manifest/v1``.  It admits an issuer only after a
verified Capital Structure *complete-submission* manifest anchors that CIK,
retains one exact Company Facts JSON response by SHA-256, and publishes a
telemetry-last coverage receipt.  It does not parse facts into observations or
write the share-count ledger; that later consumer must bind this manifest.

The scheduler serializes this adapter with the other SEC adapters.  A local
100ms floor remains here as a second, process-local fair-access guard.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
import fcntl
import hmac
import io
import json
import logging
import math
import os
from pathlib import Path
import stat
import threading
import time
from typing import Any, Iterator, Protocol

import pandas as pd
import requests

from collectors.base import Adapter, is_connection_error
from engine.capital_structure.source_identity import (
    validate_manifest_identity,
    validate_manifest_ledger,
)
from engine.capital_structure.source_store import object_key_for_sha256


log = logging.getLogger(__name__)

GROUP = "capital_structure"
POLICY_VERSION = "capital-structure-companyfacts-intake/1.2.0"
SEC_DATA_ORIGIN = "https://data.sec.gov"
MAX_CIKS_PER_RUN = 24
HARD_MAX_CIKS_PER_RUN = 64
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
HARD_MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_RUN_BYTES = 256 * 1024 * 1024
HARD_MAX_RUN_BYTES = 1024 * 1024 * 1024
MAX_RUN_SECONDS = 15 * 60.0
HARD_MAX_RUN_SECONDS = 60 * 60.0
MAX_RECEIPT_CHAIN_LENGTH = 512
MAX_GENERATION_FILE_BYTES = 128 * 1024 * 1024
# Retention verification is deliberately bounded: source admission remains an
# exact put/readback, while pre-existing immutable objects receive a rotating
# audit instead of an unbounded all-history startup scan.
MAX_RETENTION_VERIFY_OBJECTS = 24
RETENTION_VERIFY_POLICY = "bounded-retention-verification/v1"
_RETENTION_VERIFY_SCHEDULE = ("current", "current", "historical")
REFRESH_AFTER = timedelta(days=7)
RETRY_AFTER = timedelta(hours=1)
DEFER_AFTER = timedelta(hours=24)
PACE_SECONDS = 0.12
MAX_ATTEMPTS = 3

_QUEUE_SCHEDULE = ("retry_due", "new_anchor", "retry_due", "refresh_due")

SOURCE_MANIFEST_SCHEMA = "capital_structure.companyfacts_source_manifest/v1"
COVERAGE_ROW_SCHEMA = "capital_structure.companyfacts_coverage_row/v1"
COVERAGE_RECEIPT_SCHEMA = "capital_structure.companyfacts_coverage_receipt/v1"
CURRENT_POINTER_SCHEMA = "capital_structure.companyfacts_current_pointer/v1"
HEAD_WITNESS_SCHEMA = "capital_structure.companyfacts_head_witness/v1"
RECEIPT_AUTH_SCHEME = "hmac-sha256/v1"
HEAD_GUARD_KEY = "capital_structure/companyfacts/current_head.v1.json"

_SOURCE_MANIFEST_COLUMNS = [
    "schema", "manifest_id", "source_system", "source_id", "issuer", "anchor",
    "request", "retrieval", "content", "storage", "rights", "privacy", "parser",
    "spans", "authority",
]
_COVERAGE_COLUMNS = [
    "schema", "coverage_id", "attempt_id", "cik", "anchor_manifest_id", "anchor_first_seen_at",
    "attempted_at", "attempt_count", "queue_reason", "state", "retry_after", "error",
    "result",
]

_NONCLAIMS = [
    "No Company Facts value is interpreted, normalized, or added to a share-count ledger by this intake lane.",
    "No outstanding-share, public-float, fully-diluted-share, capacity, or dilution estimate is produced.",
    "No instrument, shelf, ATM, warrant, convertible, cash-runway, or financing-state assertion is produced.",
    "No risk score, offering probability, rank, sizing, entry, exit, alert, or Prophet authority is granted.",
    "A Company Facts response is current-source evidence, not historical SEC availability or point-in-time share-count proof.",
    "Only CIKs with verified Capital Structure complete-submission anchors are in scope; this is not market-wide Company Facts coverage.",
]


class CompanyFactsIntakeError(RuntimeError):
    """The bounded Company Facts source intake cannot safely continue."""


class CompanyFactsResponseTooLarge(CompanyFactsIntakeError):
    """The SEC response exceeded its declared or streamed byte ceiling."""


class CompanyFactsDeferred(CompanyFactsIntakeError):
    """A data-level error should remain visible and retry later, not become a fact."""


class CompanyFactsRunBudgetExceeded(CompanyFactsDeferred):
    """The bounded run exhausted its byte or wall-clock budget."""

    def __init__(self, message: str, *, retry_after_at: datetime | None = None) -> None:
        super().__init__(message)
        self.retry_after_at = retry_after_at


class CompanyFactsPathMissing(CompanyFactsIntakeError):
    """A securely traversed Company Facts directory component is absent."""


class CompanyFactsAnchorVerificationError(CompanyFactsDeferred):
    """A filing anchor's declared immutable bytes could not be verified exactly."""


class CompanyFactsPublishIndeterminate(CompanyFactsIntakeError):
    """A publication crossed an OS durability boundary and needs operator recovery."""


class CompanyFactsRetryable(CompanyFactsIntakeError):
    """A retryable SEC failure, optionally carrying the server retry deadline."""

    def __init__(self, message: str, *, retry_after_at: datetime | None = None) -> None:
        super().__init__(message)
        self.retry_after_at = retry_after_at


class CompanyFactsSigner(Protocol):
    """Authenticates receipts and externally witnessed heads."""

    @property
    def key_id(self) -> str: ...

    def sign(self, payload: bytes) -> str: ...

    def verify(self, payload: bytes, signature: str, *, key_id: str) -> bool: ...


class HmacCompanyFactsSigner:
    """HMAC signer whose key deliberately never lives with published artifacts."""

    def __init__(self, secret: str | bytes, *, key_id: str) -> None:
        raw = secret.encode("utf-8") if isinstance(secret, str) else secret
        if not isinstance(raw, bytes) or len(raw) < 32:
            raise ValueError("Company Facts signing secret must contain at least 32 bytes")
        if not isinstance(key_id, str) or not key_id.strip():
            raise ValueError("Company Facts signer key_id is required")
        self._secret = raw
        self._key_id = key_id.strip()

    @property
    def key_id(self) -> str:
        return self._key_id

    def sign(self, payload: bytes) -> str:
        return hmac.new(self._secret, b"companyfacts-head-v1\0" + payload, sha256).hexdigest()

    def verify(self, payload: bytes, signature: str, *, key_id: str) -> bool:
        return key_id == self.key_id and isinstance(signature, str) and hmac.compare_digest(
            self.sign(payload), signature
        )


class DeterministicTestCompanyFactsSigner(HmacCompanyFactsSigner):
    """Explicit test-only signer; production uses the env-backed signer below."""


class CompanyFactsHeadGuard(Protocol):
    """External compare-and-swap witness for the selected receipt head."""

    def read(self) -> tuple[dict[str, Any] | None, str | None]: ...

    def advance(
        self, *, expected: Mapping[str, Any] | None, expected_token: str | None,
        candidate: Mapping[str, Any],
    ) -> None: ...


class InMemoryCompanyFactsHeadGuard:
    """Deterministic CAS witness for tests only; never selected by production config."""

    def __init__(self, signer: CompanyFactsSigner) -> None:
        self._signer = signer
        self._witness: dict[str, Any] | None = None
        self._version = 0

    def read(self) -> tuple[dict[str, Any] | None, str | None]:
        if self._witness is None:
            return None, None
        _validate_head_witness(self._witness, signer=self._signer)
        return dict(self._witness), str(self._version)

    def advance(
        self, *, expected: Mapping[str, Any] | None, expected_token: str | None,
        candidate: Mapping[str, Any],
    ) -> None:
        observed, token = self.read()
        if observed != (dict(expected) if expected is not None else None) or token != expected_token:
            raise CompanyFactsIntakeError("Company Facts head witness compare-and-swap conflict")
        _validate_head_transition(previous=observed, candidate=candidate, signer=self._signer)
        self._witness = dict(candidate)
        self._version += 1


class R2CompanyFactsHeadGuard:
    """R2-backed externally witnessed, exact-predecessor Company Facts head."""

    def __init__(self, *, client: Any, bucket: str, signer: CompanyFactsSigner, key: str = HEAD_GUARD_KEY) -> None:
        if not bucket:
            raise ValueError("Company Facts head-guard bucket is required")
        self._client = client
        self._bucket = bucket
        self._signer = signer
        self._key = key

    def read(self) -> tuple[dict[str, Any] | None, str | None]:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=self._key)
        except Exception as exc:  # noqa: BLE001
            if _is_not_found_error(exc):
                return None, None
            raise CompanyFactsIntakeError("Company Facts external head witness is unreadable") from exc
        try:
            body = response["Body"].read()
            witness = _native(json.loads(body))
            if body != _canonical_bytes(witness) + b"\n":
                raise CompanyFactsIntakeError("Company Facts external head witness bytes are not canonical")
            _validate_head_witness(witness, signer=self._signer)
            # Preserve the service-supplied ETag syntax. The S3/R2 conditional
            # request header is an entity-tag and SDK callers conventionally pass
            # the quoted value returned by GetObject straight back as IfMatch.
            token = str(response.get("ETag") or "").strip()
            if not token:
                raise CompanyFactsIntakeError("Company Facts external head witness has no CAS token")
            return dict(witness), token
        except CompanyFactsIntakeError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise CompanyFactsIntakeError("Company Facts external head witness is malformed") from exc

    def advance(
        self, *, expected: Mapping[str, Any] | None, expected_token: str | None,
        candidate: Mapping[str, Any],
    ) -> None:
        observed, token = self.read()
        normalized_expected = dict(expected) if expected is not None else None
        if observed != normalized_expected or token != expected_token:
            raise CompanyFactsIntakeError("Company Facts external head witness compare-and-swap conflict")
        _validate_head_transition(previous=observed, candidate=candidate, signer=self._signer)
        arguments: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": self._key,
            "Body": _canonical_bytes(dict(candidate)) + b"\n",
            "ContentType": "application/json",
        }
        if token is None:
            arguments["IfNoneMatch"] = "*"
        else:
            arguments["IfMatch"] = token
        try:
            self._client.put_object(**arguments)
        except Exception as exc:  # noqa: BLE001
            if _is_conditional_write_conflict(exc):
                raise CompanyFactsIntakeError(
                    "Company Facts external head witness compare-and-swap conflict"
                ) from exc
            raise CompanyFactsIntakeError("Company Facts external head witness CAS failed") from exc
        confirmed, _ = self.read()
        if confirmed != dict(candidate):
            raise CompanyFactsIntakeError("Company Facts external head witness read-back mismatch")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _strict_utc(value: datetime, *, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise CompanyFactsIntakeError(f"{field} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    stamp = _strict_utc(value, field="timestamp")
    rendered = stamp.isoformat(timespec="microseconds" if stamp.microsecond else "seconds")
    return rendered.replace("+00:00", "Z")


def _data_root() -> Path:
    from lib import config

    return config.data_dir() / GROUP / "companyfacts"


def _ua() -> str:
    try:
        from collectors.edgar import _cfg

        return _cfg()["user_agent"]
    except Exception:  # noqa: BLE001
        return "Macro Dashboard research longr2512@gmail.com"


def canonical_cik(value: object) -> str:
    """Return a strict zero-padded SEC CIK without consulting any universe."""
    raw = str(value or "").strip()
    if not raw.isdigit() or len(raw) > 10 or int(raw) == 0:
        raise CompanyFactsDeferred(f"invalid CIK: {value!r}")
    return raw.zfill(10)


def companyfacts_url(cik: object) -> str:
    return f"{SEC_DATA_ORIGIN}/api/xbrl/companyfacts/CIK{canonical_cik(cik)}.json"


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _is_not_found_error(error: Exception) -> bool:
    """Recognize only authoritative S3/R2 not-found responses."""
    try:
        from botocore.exceptions import ClientError
    except ImportError:
        return False
    if not isinstance(error, ClientError):
        return False
    response = getattr(error, "response", None)
    details = response.get("Error") if isinstance(response, Mapping) else None
    return isinstance(details, Mapping) and str(details.get("Code") or "") in {
        "404", "NoSuchKey", "NotFound",
    }


def _is_conditional_write_conflict(error: Exception) -> bool:
    """Recognize the S3/R2 precondition responses that make a CAS lose."""
    response = getattr(error, "response", None)
    details = response.get("Error") if isinstance(response, Mapping) else None
    code = str(details.get("Code") or "") if isinstance(details, Mapping) else ""
    metadata = response.get("ResponseMetadata") if isinstance(response, Mapping) else None
    status = metadata.get("HTTPStatusCode") if isinstance(metadata, Mapping) else None
    return code in {"409", "412", "ConditionalRequestConflict", "PreconditionFailed"} or status in {409, 412}


def _receipt_identity_material(record: Mapping[str, Any]) -> dict[str, Any]:
    """Stable content identity excludes only mutable authentication bytes."""
    material = _native(dict(record))
    material.pop("receipt_id", None)
    auth = material.get("auth")
    if isinstance(auth, Mapping):
        auth = dict(auth)
        auth.pop("signature", None)
        material["auth"] = auth
    return material


def _receipt_auth_payload(record: Mapping[str, Any]) -> bytes:
    material = _native(dict(record))
    auth = material.get("auth")
    if not isinstance(auth, Mapping):
        raise CompanyFactsIntakeError("Company Facts receipt has no authentication envelope")
    auth = dict(auth)
    auth.pop("signature", None)
    material["auth"] = auth
    return _canonical_bytes({"domain": "capital_structure.companyfacts_receipt/v1", "receipt": material})


def _sign_receipt(record: Mapping[str, Any], *, signer: CompanyFactsSigner) -> dict[str, Any]:
    signed = _native(dict(record))
    auth = signed.get("auth")
    if not isinstance(auth, Mapping):
        raise CompanyFactsIntakeError("Company Facts receipt has no authentication envelope")
    if auth.get("scheme") != RECEIPT_AUTH_SCHEME or auth.get("key_id") != signer.key_id:
        raise CompanyFactsIntakeError("Company Facts receipt signer identity mismatch")
    signed["receipt_id"] = _receipt_id(signed)
    signed["auth"] = {**dict(auth), "signature": signer.sign(_receipt_auth_payload(signed))}
    return signed


def _validate_receipt_authentication(record: Mapping[str, Any], *, signer: CompanyFactsSigner) -> None:
    auth = record.get("auth")
    if not isinstance(auth, Mapping):
        raise CompanyFactsIntakeError("Company Facts receipt has no authentication envelope")
    if auth.get("scheme") != RECEIPT_AUTH_SCHEME:
        raise CompanyFactsIntakeError("Company Facts receipt authentication scheme is invalid")
    key_id = auth.get("key_id")
    signature = auth.get("signature")
    if not isinstance(key_id, str) or not isinstance(signature, str) or not signer.verify(
        _receipt_auth_payload(record), signature, key_id=key_id
    ):
        raise CompanyFactsIntakeError("Company Facts receipt authentication mismatch")


def _head_witness_payload(record: Mapping[str, Any]) -> bytes:
    material = _native(dict(record))
    material.pop("signature", None)
    return _canonical_bytes({"domain": "capital_structure.companyfacts_head_witness/v1", "witness": material})


def _head_witness(
    *, receipt: Mapping[str, Any], receipt_file: Mapping[str, Any], signer: CompanyFactsSigner,
) -> dict[str, Any]:
    previous = receipt.get("previous_receipt")
    record: dict[str, Any] = {
        "schema": HEAD_WITNESS_SCHEMA,
        "key_id": signer.key_id,
        "sequence": int(receipt["sequence"]),
        "receipt_id": receipt["receipt_id"],
        "receipt_sha256": receipt_file["sha256"],
        "receipt_byte_length": receipt_file["byte_length"],
        "generation_id": receipt["generation"]["generation_id"],
        "published_at": receipt["published_at"],
        "previous_receipt_id": previous.get("receipt_id") if isinstance(previous, Mapping) else None,
    }
    record["signature"] = signer.sign(_head_witness_payload(record))
    _validate_head_witness(record, signer=signer)
    return record


def _validate_head_witness(record: Mapping[str, Any], *, signer: CompanyFactsSigner) -> None:
    expected = {
        "schema", "key_id", "sequence", "receipt_id", "receipt_sha256", "receipt_byte_length",
        "generation_id", "published_at", "previous_receipt_id", "signature",
    }
    if set(record) != expected or record.get("schema") != HEAD_WITNESS_SCHEMA:
        raise CompanyFactsIntakeError("Company Facts external head witness shape is invalid")
    if not isinstance(record.get("sequence"), int) or int(record["sequence"]) < 1:
        raise CompanyFactsIntakeError("Company Facts external head witness sequence is invalid")
    for field, prefix in (("receipt_id", "receipt:cs-companyfacts:"), ("generation_id", "generation:cs-companyfacts:")):
        value = str(record.get(field) or "")
        digest = value.removeprefix(prefix)
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise CompanyFactsIntakeError("Company Facts external head witness identity is invalid")
    for field in ("receipt_sha256",):
        value = str(record.get(field) or "")
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise CompanyFactsIntakeError("Company Facts external head witness digest is invalid")
    if not isinstance(record.get("receipt_byte_length"), int) or int(record["receipt_byte_length"]) < 1:
        raise CompanyFactsIntakeError("Company Facts external head witness length is invalid")
    _parse_stamp(record.get("published_at"), field="external head witness published_at")
    previous = record.get("previous_receipt_id")
    if previous is not None:
        digest = str(previous).removeprefix("receipt:cs-companyfacts:")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise CompanyFactsIntakeError("Company Facts external head witness predecessor is invalid")
    key_id, signature = record.get("key_id"), record.get("signature")
    if not isinstance(key_id, str) or not isinstance(signature, str) or not signer.verify(
        _head_witness_payload(record), signature, key_id=key_id
    ):
        raise CompanyFactsIntakeError("Company Facts external head witness authentication mismatch")


def _validate_head_transition(
    *, previous: Mapping[str, Any] | None, candidate: Mapping[str, Any], signer: CompanyFactsSigner,
) -> None:
    _validate_head_witness(candidate, signer=signer)
    if previous is None:
        if candidate["sequence"] != 1 or candidate["previous_receipt_id"] is not None:
            raise CompanyFactsIntakeError("Company Facts external head genesis transition is invalid")
        return
    _validate_head_witness(previous, signer=signer)
    if (
        int(candidate["sequence"]) != int(previous["sequence"]) + 1
        or candidate["previous_receipt_id"] != previous["receipt_id"]
    ):
        raise CompanyFactsIntakeError("Company Facts external head transition is not exact-predecessor")


def _build_production_trust_context() -> tuple[CompanyFactsSigner, CompanyFactsHeadGuard]:
    """Return the only production trust path; absent secret/witness is a hard stop."""
    secret = os.environ.get("CAPITAL_STRUCTURE_COMPANYFACTS_HEAD_HMAC_KEY", "")
    key_id = os.environ.get("CAPITAL_STRUCTURE_COMPANYFACTS_HEAD_KEY_ID") or "companyfacts-head-v1"
    bucket = (
        os.environ.get("COMPANYFACTS_HEAD_GUARD_BUCKET")
        or os.environ.get("R2_CAPITAL_STRUCTURE_BUCKET")
        or os.environ.get("R2_BUCKET")
    )
    if not secret or not bucket:
        raise CompanyFactsIntakeError(
            "Company Facts production trust is unconfigured: require "
            "CAPITAL_STRUCTURE_COMPANYFACTS_HEAD_HMAC_KEY and a head-guard R2 bucket"
        )
    try:
        signer = HmacCompanyFactsSigner(secret, key_id=key_id)
        from engine.capital_structure.source_store import _capital_structure_r2_client

        client = _capital_structure_r2_client()
        if client is None:
            raise CompanyFactsIntakeError("Company Facts external head witness R2 client is unavailable")
        return signer, R2CompanyFactsHeadGuard(client=client, bucket=bucket, signer=signer)
    except CompanyFactsIntakeError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise CompanyFactsIntakeError("Company Facts production trust is unconfigured") from exc


def _native(value: Any) -> Any:
    """Normalize Parquet nested values before identity/hash comparisons."""
    if isinstance(value, Mapping):
        return {str(key): _native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_native(item) for item in value]
    tolist = getattr(value, "tolist", None)
    if callable(tolist) and not isinstance(value, (str, bytes, bytearray)):
        try:
            return _native(tolist())
        except Exception:  # noqa: BLE001
            pass
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    item = getattr(value, "item", None)
    if callable(item) and not isinstance(value, (str, bytes, bytearray)):
        try:
            return item()
        except Exception:  # noqa: BLE001
            pass
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [_native(record) for record in frame.to_dict(orient="records")]


def _read_ledger(path: Path, columns: Sequence[str]) -> pd.DataFrame:
    try:
        with _open_absolute_directory(path.parent) as parent_fd:
            body = _read_regular_bytes_at(
                parent_fd, path.name, label=f"ledger {path.name}", missing_ok=True,
            )
    except CompanyFactsPathMissing:
        return pd.DataFrame(columns=list(columns))
    if body is None:
        return pd.DataFrame(columns=list(columns))
    return _read_ledger_bytes(body, columns, label=str(path))


def _read_ledger_bytes(body: bytes, columns: Sequence[str], *, label: str) -> pd.DataFrame:
    """Parse a parquet ledger already read through the no-follow boundary."""
    try:
        frame = pd.read_parquet(io.BytesIO(body))
    except Exception as exc:  # noqa: BLE001
        raise CompanyFactsIntakeError(f"unreadable Company Facts ledger {label}: {exc}") from exc
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise CompanyFactsIntakeError(f"Company Facts ledger {label} lacks columns: {', '.join(missing)}")
    if list(columns) == _COVERAGE_COLUMNS:
        # Arrow promotes a nested nullable integer to float when one outcome has
        # ``byte_length=null``. Restore the contract-native integer before the
        # ordered-prefix digest is checked (mixed retrieved/deferred generations).
        frame = frame.copy()

        def normalize_result(value: Any) -> Any:
            result = _native(value)
            if isinstance(result, Mapping):
                result = dict(result)
                length = result.get("byte_length")
                if isinstance(length, float) and math.isfinite(length) and length.is_integer():
                    result["byte_length"] = int(length)
            return result

        frame["result"] = frame["result"].map(normalize_result)
    return frame[list(columns)]


def _safe_relative_parts(relative: str | Path) -> tuple[str, ...]:
    candidate = Path(relative)
    if candidate.is_absolute() or not candidate.parts:
        raise CompanyFactsIntakeError("Company Facts path must be root-relative")
    parts = tuple(candidate.parts)
    if any(part in {"", ".", ".."} or "/" in part or "\\" in part for part in parts):
        raise CompanyFactsIntakeError("Company Facts path traversal is forbidden")
    return parts


def _relative_parts(root: Path, path: Path) -> tuple[str, ...]:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise CompanyFactsIntakeError("Company Facts path escapes configured root") from exc
    return _safe_relative_parts(relative)


_DIRECTORY_OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


def _open_verified_directory_component(
    parent_fd: int, part: str, *, create: bool, label: str,
) -> int:
    """lstat/openat one component and prove the opened inode is the checked inode."""
    if part in {"", ".", ".."} or "/" in part or "\\" in part:
        raise CompanyFactsIntakeError("Company Facts path traversal is forbidden")
    try:
        checked = os.stat(part, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        if not create:
            raise CompanyFactsPathMissing(f"Company Facts directory is missing: {label}") from None
        try:
            os.mkdir(part, mode=0o700, dir_fd=parent_fd)
            os.fsync(parent_fd)
        except FileExistsError:
            # An uncooperative writer won the create race. Re-lstat and accept
            # only a real directory whose identity survives the no-follow open.
            pass
        try:
            checked = os.stat(part, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise CompanyFactsIntakeError(
                f"Company Facts directory vanished during secure creation: {label}"
            ) from exc
    if stat.S_ISLNK(checked.st_mode) or not stat.S_ISDIR(checked.st_mode):
        raise CompanyFactsIntakeError(
            f"Company Facts directory cannot be opened without following links: {label}"
        )
    try:
        descriptor = os.open(part, _DIRECTORY_OPEN_FLAGS, dir_fd=parent_fd)
    except OSError as exc:
        raise CompanyFactsIntakeError(
            f"Company Facts directory cannot be opened without following links: {label}"
        ) from exc
    opened = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or (opened.st_dev, opened.st_ino) != (checked.st_dev, checked.st_ino)
    ):
        os.close(descriptor)
        raise CompanyFactsIntakeError(f"Company Facts directory changed during secure open: {label}")
    return descriptor


@contextmanager
def _open_absolute_directory(path: Path, *, create: bool = False) -> Iterator[int]:
    """Traverse/create an absolute directory from ``/`` via no-follow dirfds."""
    if not path.is_absolute() or path.anchor != "/":
        raise CompanyFactsIntakeError("Company Facts root must be an absolute POSIX path")
    components = path.parts[1:]
    descriptors: list[int] = []
    try:
        anchor_fd = os.open("/", _DIRECTORY_OPEN_FLAGS)
        descriptors.append(anchor_fd)
        current = anchor_fd
        rendered: list[str] = []
        for part in components:
            rendered.append(part)
            current = _open_verified_directory_component(
                current, part, create=create, label="/" + "/".join(rendered),
            )
            descriptors.append(current)
        yield current
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


@contextmanager
def _open_companyfacts_directory(
    root: Path, parts: Sequence[str] = (), *, create: bool = False,
) -> Iterator[int]:
    """Open the absolute lane root and all descendants without following links.

    The root itself is never created with ``Path.mkdir(parents=True)``. Every
    ancestor starts at the trusted filesystem root and crosses an lstat/openat
    identity check, so a missing lane beneath an ancestor symlink cannot escape.
    """
    descriptors: list[int] = []
    with _open_absolute_directory(root, create=create) as root_fd:
        try:
            current = root_fd
            rendered: list[str] = []
            for part in parts:
                rendered.append(part)
                current = _open_verified_directory_component(
                    current, part, create=create, label="/".join(rendered),
                )
                descriptors.append(current)
            yield current
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)


@contextmanager
def _open_companyfacts_parent(
    root: Path, parts: Sequence[str], *, create: bool = False,
) -> Iterator[tuple[int, str]]:
    if not parts:
        raise CompanyFactsIntakeError("Company Facts file path is required")
    if any(part in {"", ".", ".."} or "/" in part or "\\" in part for part in parts):
        raise CompanyFactsIntakeError("Company Facts path traversal is forbidden")
    with _open_companyfacts_directory(root, parts[:-1], create=create) as parent_fd:
        yield parent_fd, parts[-1]


def _read_regular_bytes_at(
    parent_fd: int, name: str, *, label: str, max_bytes: int | None = None,
    missing_ok: bool = False,
) -> bytes | None:
    try:
        descriptor = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise CompanyFactsIntakeError(f"Company Facts {label} is missing") from None
    except OSError as exc:
        raise CompanyFactsIntakeError(f"Company Facts {label} cannot be opened without following links") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise CompanyFactsIntakeError(f"Company Facts {label} must be a regular file")
        if max_bytes is not None and metadata.st_size > max_bytes:
            raise CompanyFactsIntakeError(f"Company Facts {label} exceeds byte cap")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        body = b"".join(chunks)
        if len(body) != metadata.st_size:
            raise CompanyFactsIntakeError(f"Company Facts {label} changed during secure read")
        return body
    finally:
        os.close(descriptor)


def _write_new_regular_bytes_at(parent_fd: int, name: str, content: bytes, *, label: str) -> None:
    try:
        descriptor = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_fd,
        )
    except OSError as exc:
        raise CompanyFactsIntakeError(f"cannot securely create Company Facts {label}") from exc
    try:
        offset = 0
        while offset < len(content):
            offset += os.write(descriptor, content[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    with _open_absolute_directory(path) as descriptor:
        os.fsync(descriptor)


@contextmanager
def _companyfacts_publish_lease(root: Path) -> Iterator[None]:
    """Mandatory cross-process lease spanning load, network work, and publish.

    The external R2 witness remains the cross-host CAS authority; this lock
    prevents two local processes from doing duplicate network work or forking
    the on-disk receipt chain before that CAS point.
    """
    with _open_companyfacts_directory(root, create=True) as root_fd:
        try:
            lock_fd = os.open(
                ".companyfacts_publish.lock",
                os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=root_fd,
            )
        except OSError as exc:
            raise CompanyFactsIntakeError("Company Facts publish lease cannot follow a symlink") from exc
        try:
            if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
                raise CompanyFactsIntakeError("Company Facts publish lease must be a regular file")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)


def _atomic_write_bytes(
    path: Path, content: bytes, *, expected_previous: bytes | None | object = ...,
    root: Path | None = None,
) -> None:
    """Atomically replace a pointer under an exact-predecessor publication lease.

    A directory-fsync failure is intentionally *not* softened: visibility after
    ``os.replace`` is not a durability acknowledgement. The external head witness
    records the recovery target, while this call reports an indeterminate publish.
    """
    safe_root = root or path.parent
    parts = _relative_parts(safe_root, path) if root is not None else _safe_relative_parts(path.name)
    temporary = f".{parts[-1]}.{os.getpid()}.{time.time_ns()}.tmp"
    with _open_companyfacts_parent(safe_root, parts, create=True) as (parent_fd, name):
        previous = _read_regular_bytes_at(parent_fd, name, label="current pointer", missing_ok=True)
        if expected_previous is not ... and previous != expected_previous:
            raise CompanyFactsIntakeError(f"Company Facts pointer exact-predecessor CAS conflict: {path}")
        try:
            _write_new_regular_bytes_at(parent_fd, temporary, content, label="staged pointer")
            if _read_regular_bytes_at(parent_fd, temporary, label="staged pointer") != content:
                raise CompanyFactsIntakeError(f"staged pointer read-back mismatch: {path}")
            try:
                # Re-check via the same parent descriptor immediately before commit.
                if expected_previous is not ...:
                    observed = _read_regular_bytes_at(parent_fd, name, label="current pointer", missing_ok=True)
                    if observed != expected_previous:
                        raise CompanyFactsIntakeError(
                            f"Company Facts pointer exact-predecessor CAS conflict: {path}"
                        )
                os.replace(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            except Exception:
                actual = _read_regular_bytes_at(parent_fd, name, label="current pointer", missing_ok=True)
                if actual != previous:
                    raise CompanyFactsIntakeError(f"Company Facts pointer state uncertain: {path}")
                raise
            try:
                os.fsync(parent_fd)
                # Preserve the explicit path-level fsync seam for operator fault
                # injection, but the descriptor fsync above is the safety boundary.
                _fsync_directory(path.parent)
            except Exception as exc:
                raise CompanyFactsPublishIndeterminate(
                    f"Company Facts pointer durability is indeterminate after replace: {path}"
                ) from exc
        finally:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass


def _write_immutable_bytes(path: Path, content: bytes, *, root: Path | None = None) -> None:
    """Create one immutable object without ever replacing a divergent target."""
    safe_root = root or path.parent
    parts = _relative_parts(safe_root, path) if root is not None else _safe_relative_parts(path.name)
    temporary = f".{parts[-1]}.{os.getpid()}.{time.time_ns()}.tmp"
    with _open_companyfacts_parent(safe_root, parts, create=True) as (parent_fd, name):
        existing = _read_regular_bytes_at(parent_fd, name, label="immutable object", missing_ok=True)
        if existing is not None:
            if existing != content:
                raise CompanyFactsIntakeError(f"immutable Company Facts object collision: {path}")
            return
        try:
            _write_new_regular_bytes_at(parent_fd, temporary, content, label="immutable staged object")
            if _read_regular_bytes_at(parent_fd, temporary, label="immutable staged object") != content:
                raise CompanyFactsIntakeError(f"immutable Company Facts object read-back mismatch: {path}")
            try:
                os.link(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd, follow_symlinks=False)
            except FileExistsError:
                existing = _read_regular_bytes_at(parent_fd, name, label="immutable object")
                if existing != content:
                    raise CompanyFactsIntakeError(f"immutable Company Facts object collision: {path}")
            os.fsync(parent_fd)
            _fsync_directory(path.parent)
        finally:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass


def _ledger_receipt(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Hash the exact append order so the digest is an ordered-prefix proof."""
    canonical = [_canonical_bytes(dict(record)) for record in records]
    digest = sha256(b"".join(chunk + b"\n" for chunk in canonical)).hexdigest()
    return {"record_count": len(canonical), "prefix_sha256": digest, "immutable_prefix": True}


def _file_receipt(path: Path, *, root: Path | None = None, max_bytes: int | None = None) -> dict[str, Any]:
    if root is None:
        body = path.read_bytes()
    else:
        parts = _relative_parts(root, path)
        with _open_companyfacts_parent(root, parts) as (parent_fd, name):
            body = _read_regular_bytes_at(parent_fd, name, label="file receipt", max_bytes=max_bytes)
            assert body is not None
    return {"sha256": sha256(body).hexdigest(), "byte_length": len(body)}


def _bytes_receipt(body: bytes) -> dict[str, Any]:
    return {"sha256": sha256(body).hexdigest(), "byte_length": len(body)}


def _generation_id(
    *, source_file: Mapping[str, Any], coverage_file: Mapping[str, Any],
    source_ledger: Mapping[str, Any], coverage_ledger: Mapping[str, Any],
) -> str:
    material = {
        "schema": "capital_structure.companyfacts_generation/v1",
        "source_manifest_file": dict(source_file),
        "coverage_file": dict(coverage_file),
        "source_manifest_ledger": dict(source_ledger),
        "coverage_ledger": dict(coverage_ledger),
    }
    return "generation:cs-companyfacts:" + sha256(_canonical_bytes(material)).hexdigest()


@dataclass(frozen=True)
class _PreparedGeneration:
    descriptor: dict[str, Any]
    stage_path: Path | None


def _generation_descriptor(
    *, source_file: Mapping[str, Any], coverage_file: Mapping[str, Any],
    source_ledger: Mapping[str, Any], coverage_ledger: Mapping[str, Any],
) -> dict[str, Any]:
    generation_id = _generation_id(
        source_file=source_file, coverage_file=coverage_file,
        source_ledger=source_ledger, coverage_ledger=coverage_ledger,
    )
    digest = generation_id.rsplit(":", 1)[-1]
    return {
        "generation_id": generation_id,
        "source_manifest": {
            "path": f"generations/{digest}/source_manifest.parquet",
            **dict(source_file),
        },
        "coverage": {
            "path": f"generations/{digest}/coverage.parquet",
            **dict(coverage_file),
        },
    }


def _prepare_generation(
    *, source_manifests: pd.DataFrame, coverage: pd.DataFrame, root: Path,
    prior_receipt: Mapping[str, Any] | None, deadline: float | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> _PreparedGeneration:
    source_records = _records(source_manifests)
    coverage_records = _records(coverage)
    source_ledger = _ledger_receipt(source_records)
    coverage_ledger = _ledger_receipt(coverage_records)
    if prior_receipt is not None:
        if (
            prior_receipt.get("companyfacts_manifest_ledger") == source_ledger
            and prior_receipt.get("coverage_ledger") == coverage_ledger
        ):
            descriptor = prior_receipt.get("generation")
            if not isinstance(descriptor, Mapping):
                raise CompanyFactsIntakeError("prior receipt has no immutable generation descriptor")
            return _PreparedGeneration(descriptor=dict(descriptor), stage_path=None)

    stage_name = f".generation-stage-{os.getpid()}-{time.time_ns()}"
    stage = root / stage_name
    with _open_companyfacts_directory(root, create=True) as root_fd:
        try:
            os.mkdir(stage_name, mode=0o700, dir_fd=root_fd)
        except FileExistsError as exc:
            raise CompanyFactsIntakeError("Company Facts generation stage collision") from exc
    try:
        if deadline is not None and monotonic() >= deadline:
            raise CompanyFactsRunBudgetExceeded("Company Facts generation seal exceeded run deadline")
        manifest_body = source_manifests.to_parquet(index=False)
        coverage_body = coverage.to_parquet(index=False)
        if not isinstance(manifest_body, bytes) or not isinstance(coverage_body, bytes):
            raise CompanyFactsIntakeError("Company Facts parquet encoder did not return immutable bytes")
        for label, body in (("source_manifest.parquet", manifest_body), ("coverage.parquet", coverage_body)):
            if len(body) > MAX_GENERATION_FILE_BYTES:
                raise CompanyFactsIntakeError(
                    f"Company Facts generation file exceeds {MAX_GENERATION_FILE_BYTES} byte cap: {label}"
                )
        with _open_companyfacts_directory(root, (stage_name,)) as stage_fd:
            _write_new_regular_bytes_at(stage_fd, "source_manifest.parquet", manifest_body, label="staged source manifest")
            _write_new_regular_bytes_at(stage_fd, "coverage.parquet", coverage_body, label="staged coverage")
            manifest_body = _read_regular_bytes_at(
                stage_fd, "source_manifest.parquet", label="staged source manifest",
                max_bytes=MAX_GENERATION_FILE_BYTES,
            )
            coverage_body = _read_regular_bytes_at(
                stage_fd, "coverage.parquet", label="staged coverage",
                max_bytes=MAX_GENERATION_FILE_BYTES,
            )
            assert manifest_body is not None and coverage_body is not None
            os.fsync(stage_fd)
        if deadline is not None and monotonic() >= deadline:
            raise CompanyFactsRunBudgetExceeded("Company Facts generation seal exceeded run deadline")
        published_manifests = _read_ledger_bytes(manifest_body, _SOURCE_MANIFEST_COLUMNS, label="staged source manifest")
        published_coverage = _read_ledger_bytes(coverage_body, _COVERAGE_COLUMNS, label="staged coverage")
        if _ledger_receipt(_records(published_manifests)) != source_ledger:
            raise CompanyFactsIntakeError("staged Company Facts manifest ledger read-back mismatch")
        if _ledger_receipt(_records(published_coverage)) != coverage_ledger:
            raise CompanyFactsIntakeError("staged Company Facts coverage ledger read-back mismatch")
        descriptor = _generation_descriptor(
            source_file=_bytes_receipt(manifest_body), coverage_file=_bytes_receipt(coverage_body),
            source_ledger=source_ledger, coverage_ledger=coverage_ledger,
        )
        _fsync_directory(stage)
        return _PreparedGeneration(descriptor=descriptor, stage_path=stage)
    except Exception:
        _discard_stage(root, stage, ignore_errors=True)
        raise


def _generation_paths(root: Path, descriptor: Mapping[str, Any]) -> tuple[Path, Path]:
    generation_id = str(descriptor.get("generation_id") or "")
    digest = generation_id.removeprefix("generation:cs-companyfacts:")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise CompanyFactsIntakeError("invalid Company Facts generation identity")
    expected_source = f"generations/{digest}/source_manifest.parquet"
    expected_coverage = f"generations/{digest}/coverage.parquet"
    source = descriptor.get("source_manifest")
    coverage = descriptor.get("coverage")
    if not isinstance(source, Mapping) or source.get("path") != expected_source:
        raise CompanyFactsIntakeError("generation source-manifest path is not identity-bound")
    if not isinstance(coverage, Mapping) or coverage.get("path") != expected_coverage:
        raise CompanyFactsIntakeError("generation coverage path is not identity-bound")
    generation_root = root / "generations" / digest
    try:
        with _open_companyfacts_directory(root, ("generations",)) as generations_fd:
            try:
                generation_fd = os.open(
                    digest,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=generations_fd,
                )
            except FileNotFoundError:
                generation_fd = None
            except OSError as exc:
                raise CompanyFactsIntakeError("Company Facts generation directory cannot follow a symlink") from exc
            if generation_fd is not None:
                try:
                    if not stat.S_ISDIR(os.fstat(generation_fd).st_mode):
                        raise CompanyFactsIntakeError("Company Facts generation path is not a directory")
                finally:
                    os.close(generation_fd)
    except CompanyFactsPathMissing:
        # A descriptor can be computed before its immutable generation is installed.
        pass
    return generation_root / "source_manifest.parquet", generation_root / "coverage.parquet"


def _validate_generation_files(root: Path, descriptor: Mapping[str, Any]) -> tuple[Path, Path]:
    source_path, coverage_path = _generation_paths(root, descriptor)
    digest = str(descriptor["generation_id"]).rsplit(":", 1)[-1]
    with _open_companyfacts_directory(root, ("generations", digest)) as generation_fd:
        for key, name in (("source_manifest", "source_manifest.parquet"), ("coverage", "coverage.parquet")):
            body = _read_regular_bytes_at(
                generation_fd, name, label=f"committed {key} generation file",
                max_bytes=MAX_GENERATION_FILE_BYTES,
            )
            assert body is not None
            expected = descriptor[key]
            if _bytes_receipt(body) != {
            "sha256": expected.get("sha256"), "byte_length": expected.get("byte_length")
            }:
                raise CompanyFactsIntakeError(f"committed Company Facts {key} exact-byte receipt mismatch")
    return source_path, coverage_path


def _generation_bodies(root: Path, descriptor: Mapping[str, Any]) -> tuple[bytes, bytes]:
    """Return exact, receipt-validated generation bytes through a no-follow chain."""
    _validate_generation_files(root, descriptor)
    digest = str(descriptor["generation_id"]).rsplit(":", 1)[-1]
    with _open_companyfacts_directory(root, ("generations", digest)) as generation_fd:
        source = _read_regular_bytes_at(
            generation_fd, "source_manifest.parquet", label="committed source manifest",
            max_bytes=MAX_GENERATION_FILE_BYTES,
        )
        coverage = _read_regular_bytes_at(
            generation_fd, "coverage.parquet", label="committed coverage",
            max_bytes=MAX_GENERATION_FILE_BYTES,
        )
        assert source is not None and coverage is not None
        return source, coverage


def _install_generation(root: Path, prepared: _PreparedGeneration) -> None:
    if prepared.stage_path is None:
        _validate_generation_files(root, prepared.descriptor)
        return
    source_path, _ = _generation_paths(root, prepared.descriptor)
    target = source_path.parent
    stage = prepared.stage_path
    try:
        digest = str(prepared.descriptor["generation_id"]).rsplit(":", 1)[-1]
        stage_parts = _relative_parts(root, stage)
        if len(stage_parts) != 1 or not stage_parts[0].startswith(".generation-stage-"):
            raise CompanyFactsIntakeError("Company Facts generation stage path is not root-bound")
        with _open_companyfacts_directory(root, create=True) as root_fd:
            with _open_companyfacts_directory(root, ("generations",), create=True) as generations_fd:
                try:
                    target_fd = os.open(
                        digest,
                        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                        dir_fd=generations_fd,
                    )
                except FileNotFoundError:
                    target_fd = None
                if target_fd is not None:
                    os.close(target_fd)
                    _validate_generation_files(root, prepared.descriptor)
                    _discard_stage(root, stage)
                else:
                    os.replace(stage_parts[0], digest, src_dir_fd=root_fd, dst_dir_fd=generations_fd)
                    os.fsync(generations_fd)
                    _fsync_directory(target.parent)
        _validate_generation_files(root, prepared.descriptor)
    except Exception:
        _discard_stage(root, stage, ignore_errors=True)
        raise


def _discard_prepared_generation(prepared: _PreparedGeneration | None) -> None:
    """Remove an unpublished stage after budget/publish failure."""
    if prepared is not None and prepared.stage_path is not None:
        root = prepared.stage_path.parent
        _discard_stage(root, prepared.stage_path, ignore_errors=True)


def _discard_stage(root: Path, stage: Path, *, ignore_errors: bool = False) -> None:
    """Delete only a no-follow, root-owned staging directory and its regular files."""
    try:
        parts = _relative_parts(root, stage)
        if len(parts) != 1 or not parts[0].startswith(".generation-stage-"):
            raise CompanyFactsIntakeError("Company Facts stage path is not root-bound")
        with _open_companyfacts_directory(root) as root_fd:
            try:
                stage_fd = os.open(
                    parts[0],
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=root_fd,
                )
            except FileNotFoundError:
                return
            try:
                for name in os.listdir(stage_fd):
                    metadata = os.stat(name, dir_fd=stage_fd, follow_symlinks=False)
                    if not stat.S_ISREG(metadata.st_mode):
                        raise CompanyFactsIntakeError("Company Facts stage contains unsafe non-file entry")
                    os.unlink(name, dir_fd=stage_fd)
            finally:
                os.close(stage_fd)
            os.rmdir(parts[0], dir_fd=root_fd)
    except Exception:
        if not ignore_errors:
            raise


def _publish_generation(
    *, root: Path, receipt_path: Path, receipt: Mapping[str, Any], prepared: _PreparedGeneration,
    signer: CompanyFactsSigner, head_guard: CompanyFactsHeadGuard,
    expected_witness: Mapping[str, Any] | None, expected_witness_token: str | None,
    expected_pointer: bytes | None,
) -> None:
    """Seal artifacts, CAS the external head, then advance the local selector."""
    _install_generation(root, prepared)
    receipt_body = _canonical_bytes(dict(receipt)) + b"\n"
    receipt_digest = str(receipt["receipt_id"]).rsplit(":", 1)[-1]
    immutable_relative = f"receipts/{receipt_digest}.json"
    immutable_path = root / immutable_relative
    _write_immutable_bytes(immutable_path, receipt_body, root=root)
    receipt_file = _file_receipt(immutable_path, root=root)
    witness = _head_witness(receipt=receipt, receipt_file=receipt_file, signer=signer)
    # This is the authoritative exact-predecessor CAS. It must precede the local
    # pointer because a missing/old local selector then fails closed rather than
    # presenting an unwitnessed new head after a power loss.
    head_guard.advance(
        expected=expected_witness,
        expected_token=expected_witness_token,
        candidate=witness,
    )
    pointer: dict[str, Any] = {
        "schema": CURRENT_POINTER_SCHEMA,
        "receipt_id": receipt["receipt_id"],
        "receipt_path": immutable_relative,
        "receipt_sha256": receipt_file["sha256"],
        "receipt_byte_length": receipt_file["byte_length"],
        "generation_id": receipt["generation"]["generation_id"],
        "published_at": receipt["published_at"],
    }
    pointer["pointer_id"] = _pointer_id(pointer)
    _validate_contract(
        pointer, "capital_structure_companyfacts_current_pointer.schema.json",
        label="Company Facts current pointer",
    )
    _validate_pointer_identity(pointer)
    pointer_body = _canonical_bytes(pointer) + b"\n"
    _atomic_write_bytes(receipt_path, pointer_body, expected_previous=expected_pointer, root=root)
    if _file_receipt(receipt_path, root=root) != _bytes_receipt(pointer_body):
        raise CompanyFactsIntakeError("Company Facts current pointer read-back mismatch")


def _authority() -> dict[str, bool]:
    return {
        "is_context_only": True,
        "share_count_ledger_authority": False,
        "instrument_authority": False,
        "capacity_authority": False,
        "runway_authority": False,
        "risk_authority": False,
        "rank_authority": False,
        "sizing_authority": False,
        "entry_authority": False,
        "prophet_authority": False,
    }


def _validate_contract(record: Mapping[str, Any], filename: str, *, label: str) -> None:
    from jsonschema import Draft202012Validator, FormatChecker

    schema_path = Path(__file__).resolve().parents[1] / "contracts" / filename
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(record),
        key=lambda error: list(error.path),
    )
    if errors:
        joined = "; ".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors[:5]
        )
        raise CompanyFactsIntakeError(f"{label} contract violation: {joined}")


def _source_manifest_id(record: Mapping[str, Any]) -> str:
    material = {key: value for key, value in record.items() if key != "manifest_id"}
    return "manifest:cs-companyfacts:" + sha256(_canonical_bytes(material)).hexdigest()


def _coverage_id(record: Mapping[str, Any]) -> str:
    material = {key: value for key, value in record.items() if key != "coverage_id"}
    return "coverage:cs-companyfacts:" + sha256(_canonical_bytes(material)).hexdigest()


def _attempt_id(record: Mapping[str, Any]) -> str:
    material = {
        "cik": record.get("cik"),
        "anchor_manifest_id": record.get("anchor_manifest_id"),
        "attempted_at": record.get("attempted_at"),
        "attempt_count": record.get("attempt_count"),
    }
    return "attempt:cs-companyfacts:" + sha256(_canonical_bytes(material)).hexdigest()


def _receipt_id(record: Mapping[str, Any]) -> str:
    return "receipt:cs-companyfacts:" + sha256(_canonical_bytes(_receipt_identity_material(record))).hexdigest()


def _pointer_id(record: Mapping[str, Any]) -> str:
    material = {key: value for key, value in record.items() if key != "pointer_id"}
    return "pointer:cs-companyfacts:" + sha256(_canonical_bytes(material)).hexdigest()


def _parse_stamp(value: object, *, field: str) -> pd.Timestamp:
    try:
        stamp = pd.Timestamp(value)
    except Exception as exc:  # noqa: BLE001
        raise CompanyFactsIntakeError(f"invalid {field}: {value!r}") from exc
    if pd.isna(stamp) or stamp.tzinfo is None or stamp.utcoffset() is None:
        raise CompanyFactsIntakeError(f"invalid {field}: {value!r}")
    return stamp.tz_convert("UTC")


def _require_body_identity(
    record: Mapping[str, Any], *, field: str, expected: str, label: str,
) -> None:
    actual = record.get(field)
    if not isinstance(actual, str) or not hmac.compare_digest(actual, expected):
        raise CompanyFactsIntakeError(f"{label} body identity mismatch")


def _validate_source_manifest_identity(record: Mapping[str, Any]) -> None:
    _require_body_identity(
        record, field="manifest_id", expected=_source_manifest_id(record),
        label="Company Facts source manifest",
    )


def _validate_coverage_identity(record: Mapping[str, Any]) -> None:
    _require_body_identity(
        record, field="coverage_id", expected=_coverage_id(record),
        label="Company Facts coverage row",
    )
    _require_body_identity(
        record, field="attempt_id", expected=_attempt_id(record),
        label="Company Facts logical attempt",
    )


def _validate_receipt_identity(record: Mapping[str, Any]) -> None:
    _require_body_identity(
        record, field="receipt_id", expected=_receipt_id(record),
        label="Company Facts current receipt",
    )


def _validate_pointer_identity(record: Mapping[str, Any]) -> None:
    _require_body_identity(
        record, field="pointer_id", expected=_pointer_id(record),
        label="Company Facts current pointer",
    )


def _anchor_candidate(record: Mapping[str, Any]) -> dict[str, Any] | None:
    issuer = record.get("issuer") if isinstance(record.get("issuer"), Mapping) else {}
    document = record.get("document") if isinstance(record.get("document"), Mapping) else {}
    retrieval = record.get("retrieval") if isinstance(record.get("retrieval"), Mapping) else {}
    storage = record.get("storage") if isinstance(record.get("storage"), Mapping) else {}
    parser = record.get("parser") if isinstance(record.get("parser"), Mapping) else {}
    if document.get("document_role") != "complete_submission":
        return None
    if retrieval.get("transport_status") != "retrieved":
        return None
    if parser.get("eligibility") != "eligible" or parser.get("corruption_state") != "clean":
        return None
    digest = str(document.get("content_sha256") or "").lower()
    if len(digest) != 64 or document.get("root_locator") != f"sha256:{digest}":
        return None
    byte_length = document.get("byte_length")
    if isinstance(byte_length, bool) or not isinstance(byte_length, int) or byte_length < 1:
        return None
    if storage.get("content_addressed") is not True or storage.get("retention_state") != "retained":
        return None
    if storage.get("object_key") != object_key_for_sha256(digest):
        return None
    store_id = storage.get("store_id")
    backend = storage.get("backend")
    if not isinstance(store_id, str) or backend not in {"local", "r2"}:
        return None
    try:
        cik = canonical_cik(issuer.get("cik"))
        first_seen = _parse_stamp(retrieval.get("first_seen_at"), field="anchor first_seen_at")
    except (CompanyFactsDeferred, CompanyFactsIntakeError):
        return None
    manifest_id = str(record.get("manifest_id") or "")
    source_id = str(record.get("source_id") or "")
    if not manifest_id or not source_id:
        return None
    validate_manifest_identity(record)
    return {
        "cik": cik,
        "manifest_id": manifest_id,
        "source_id": source_id,
        "content_sha256": digest,
        "byte_length": byte_length,
        "storage_backend": backend,
        "storage_store_id": store_id,
        "storage_object_key": storage["object_key"],
        "first_seen_at": first_seen,
        "ticker": issuer.get("ticker") if isinstance(issuer.get("ticker"), str) else None,
        "aliases": sorted({str(value) for value in issuer.get("aliases", []) if str(value)}),
    }


def _complete_submission_anchor_candidates(records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Collapse manifest-valid candidates; selected raw bytes are verified later."""
    if records:
        # Existing filing manifests retain their own strict immutable identity law.
        validate_manifest_ledger([dict(record) for record in records])
    candidates: list[dict[str, Any]] = []
    for raw in records:
        record = _native(raw)
        candidate = _anchor_candidate(record)
        if candidate is not None:
            candidates.append(candidate)
    anchors: dict[str, dict[str, Any]] = {}
    for candidate in sorted(candidates, key=lambda item: (item["cik"], item["first_seen_at"], item["manifest_id"])):
        anchors.setdefault(candidate["cik"], candidate)
    return anchors


def _anchor_storage_binding(anchor: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "cik": str(anchor["cik"]),
        "anchor_manifest_id": str(anchor["manifest_id"]),
        "backend": str(anchor["storage_backend"]),
        "store_id": str(anchor["storage_store_id"]),
        "object_key": str(anchor["storage_object_key"]),
        "content_sha256": str(anchor["content_sha256"]),
        "byte_length": int(anchor["byte_length"]),
    }


def _anchor_verification_record(
    anchor: Mapping[str, Any], *, status: str, error: str | None,
) -> dict[str, Any]:
    if status not in {"verified", "failed"} or (status == "verified") != (error is None):
        raise CompanyFactsIntakeError("invalid Company Facts anchor verification outcome")
    return {**_anchor_storage_binding(anchor), "status": status, "error": error}


def _verify_anchor_source_object(
    anchor: Mapping[str, Any], *, source_stores: Mapping[str, Any],
    deadline: float | None, monotonic: Callable[[], float],
    byte_observer: Callable[[int], None] | None = None,
    remaining_byte_budget: int | None = None,
) -> dict[str, Any]:
    """Verify the exact filing bytes before its CIK may call Company Facts."""
    binding = _anchor_storage_binding(anchor)
    try:
        expected_key = object_key_for_sha256(binding["content_sha256"])
    except ValueError as exc:
        raise CompanyFactsAnchorVerificationError("anchor content digest is invalid") from exc
    if binding["object_key"] != expected_key:
        raise CompanyFactsAnchorVerificationError("anchor object key is detached from its content digest")
    if remaining_byte_budget is not None and binding["byte_length"] > remaining_byte_budget:
        raise CompanyFactsRunBudgetExceeded("Company Facts anchor verification exceeds run byte budget")
    store = source_stores.get(binding["store_id"])
    if store is None:
        raise CompanyFactsAnchorVerificationError(
            f"anchor source store is unavailable: {binding['store_id']!r}"
        )
    if getattr(store, "store_id", None) != binding["store_id"]:
        raise CompanyFactsAnchorVerificationError("anchor source store identity is rebound")
    if getattr(store, "backend", None) != binding["backend"]:
        raise CompanyFactsAnchorVerificationError("anchor source store backend is rebound")
    try:
        body = _get_verified_before_deadline(
            store, binding["object_key"], binding["content_sha256"],
            deadline=deadline, monotonic=monotonic,
        )
    except CompanyFactsRunBudgetExceeded:
        raise
    except Exception as exc:  # noqa: BLE001
        raise CompanyFactsAnchorVerificationError("anchor source object verification failed") from exc
    if isinstance(body, bytes) and byte_observer is not None:
        byte_observer(len(body))
    if (
        not isinstance(body, bytes)
        or len(body) != binding["byte_length"]
        or sha256(body).hexdigest() != binding["content_sha256"]
    ):
        raise CompanyFactsAnchorVerificationError("anchor source object is missing or mismatched")
    return _anchor_verification_record(anchor, status="verified", error=None)


def _anchor_candidate_index(records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for raw in records:
        candidate = _anchor_candidate(_native(raw))
        if candidate is not None:
            index[candidate["manifest_id"]] = candidate
    return index


def _validate_source_manifest_semantics(
    record: Mapping[str, Any], *, anchors_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    native = _native(record)
    _validate_contract(
        native, "capital_structure_companyfacts_source_manifest.schema.json",
        label="retained Company Facts source manifest",
    )
    _validate_source_manifest_identity(native)
    issuer = native["issuer"]
    anchor = native["anchor"]
    content = native["content"]
    storage = native["storage"]
    request = native["request"]
    retrieval = native["retrieval"]
    spans = native["spans"]
    cik = canonical_cik(issuer["cik"])
    digest = str(content["content_sha256"])
    byte_length = int(content["byte_length"])
    if issuer["issuer_id"] != f"sec:cik:{cik}":
        raise CompanyFactsIntakeError("Company Facts issuer_id/CIK binding mismatch")
    if native["source_id"] != f"sec-companyfacts:{cik}:{digest}":
        raise CompanyFactsIntakeError("Company Facts source_id/CIK/hash binding mismatch")
    if request["canonical_url"] != companyfacts_url(cik):
        raise CompanyFactsIntakeError("Company Facts request URL/CIK binding mismatch")
    if content["root_locator"] != f"sha256:{digest}":
        raise CompanyFactsIntakeError("Company Facts root locator/hash binding mismatch")
    if storage["object_key"] != object_key_for_sha256(digest):
        raise CompanyFactsIntakeError("Company Facts object key/hash binding mismatch")
    expected_span = {
        "span_id": f"root:{digest}", "locator_type": "document",
        "locator": f"bytes:0-{byte_length}", "text_sha256": digest,
    }
    if spans != [expected_span]:
        raise CompanyFactsIntakeError("Company Facts root span/hash/length binding mismatch")
    anchor_id = str(anchor["capital_structure_manifest_id"])
    anchor_record = anchors_by_id.get(anchor_id)
    if anchor_record is None:
        raise CompanyFactsIntakeError("Company Facts source manifest has no verified filing anchor")
    if (
        anchor_record["cik"] != cik
        or anchor["capital_structure_source_id"] != anchor_record["source_id"]
        or anchor["complete_submission_sha256"] != anchor_record["content_sha256"]
        or int(anchor["complete_submission_byte_length"]) != int(anchor_record["byte_length"])
        or anchor["complete_submission_backend"] != anchor_record["storage_backend"]
        or anchor["complete_submission_store_id"] != anchor_record["storage_store_id"]
        or anchor["complete_submission_object_key"] != anchor_record["storage_object_key"]
        or anchor["first_seen_at"] != _iso(anchor_record["first_seen_at"])
    ):
        raise CompanyFactsIntakeError("Company Facts source/filing-anchor semantic binding mismatch")
    if issuer.get("ticker") != anchor_record.get("ticker"):
        raise CompanyFactsIntakeError("Company Facts source ticker is detached from filing anchor")
    if list(issuer.get("aliases") or []) != list(anchor_record.get("aliases") or []):
        raise CompanyFactsIntakeError("Company Facts source aliases are detached from filing anchor")
    retrieved_at = _parse_stamp(retrieval["retrieved_at"], field="source retrieved_at")
    first_seen_at = _parse_stamp(retrieval["first_seen_at"], field="source first_seen_at")
    if retrieved_at != first_seen_at or first_seen_at < anchor_record["first_seen_at"]:
        raise CompanyFactsIntakeError("Company Facts source clocks violate acquisition causality")
    return native


def _validate_companyfacts_bundle(
    *, anchor_records: Sequence[Mapping[str, Any]], source_records: Sequence[Mapping[str, Any]],
    coverage_records: Sequence[Mapping[str, Any]],
) -> None:
    if anchor_records:
        validate_manifest_ledger([dict(record) for record in anchor_records])
    anchors_by_id = _anchor_candidate_index(anchor_records)
    sources_by_id: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(source_records):
        source = _validate_source_manifest_semantics(raw, anchors_by_id=anchors_by_id)
        manifest_id = str(source["manifest_id"])
        if manifest_id in sources_by_id:
            raise CompanyFactsIntakeError(f"duplicate Company Facts manifest_id at row {index}")
        sources_by_id[manifest_id] = source

    seen_coverage_ids: set[str] = set()
    seen_attempts: dict[str, bytes] = {}
    history: dict[str, dict[str, Any]] = {}
    referenced_sources: set[str] = set()
    for index, raw in enumerate(coverage_records):
        record = _native(raw)
        _validate_contract(
            record, "capital_structure_companyfacts_coverage_row.schema.json",
            label="coverage row",
        )
        _validate_coverage_identity(record)
        coverage_id = str(record["coverage_id"])
        if coverage_id in seen_coverage_ids:
            raise CompanyFactsIntakeError(f"duplicate Company Facts coverage_id at row {index}")
        seen_coverage_ids.add(coverage_id)
        attempt_id = str(record["attempt_id"])
        encoded = _canonical_bytes(record)
        previous_attempt = seen_attempts.get(attempt_id)
        if previous_attempt is not None:
            qualifier = "divergent" if previous_attempt != encoded else "duplicate"
            raise CompanyFactsIntakeError(f"{qualifier} logical Company Facts attempt: {attempt_id}")
        seen_attempts[attempt_id] = encoded
        cik = canonical_cik(record["cik"])
        anchor = anchors_by_id.get(str(record["anchor_manifest_id"]))
        if anchor is None or anchor["cik"] != cik:
            raise CompanyFactsIntakeError("coverage row has no same-CIK verified filing anchor")
        if record["anchor_first_seen_at"] != _iso(anchor["first_seen_at"]):
            raise CompanyFactsIntakeError("coverage row anchor clock does not match filing anchor")
        attempted_at = _parse_stamp(record["attempted_at"], field="coverage attempted_at")
        prior = history.get(cik)
        if prior is None:
            if record["attempt_count"] != 1 or record["queue_reason"] != "new_anchor":
                raise CompanyFactsIntakeError("first Company Facts attempt must be new_anchor attempt 1")
        else:
            if int(record["attempt_count"]) != int(prior["attempt_count"]) + 1:
                raise CompanyFactsIntakeError("Company Facts attempt_count is not strictly monotone")
            if attempted_at < _parse_stamp(prior["attempted_at"], field="prior coverage attempted_at"):
                raise CompanyFactsIntakeError("Company Facts attempt clocks are not monotone")
            expected_reason = "retry_due" if prior["state"] in {"retry", "deferred"} else "refresh_due"
            if record["queue_reason"] != expected_reason:
                raise CompanyFactsIntakeError("Company Facts queue reason is detached from prior state")
            if prior["state"] in {"retry", "deferred"} and attempted_at < _parse_stamp(
                prior["retry_after"], field="prior retry_after"
            ):
                raise CompanyFactsIntakeError("Company Facts retry occurred before retry_after")
        history[cik] = record
        if record["state"] in {"retry", "deferred"}:
            retry_after = _parse_stamp(record["retry_after"], field="coverage retry_after")
            if retry_after <= attempted_at:
                raise CompanyFactsIntakeError("coverage retry_after must follow attempted_at")
            continue
        result = record["result"]
        source_manifest_id = str(result["source_manifest_id"])
        source = sources_by_id.get(source_manifest_id)
        if source is None:
            raise CompanyFactsIntakeError("retrieved coverage result references no source manifest")
        if source_manifest_id in referenced_sources:
            raise CompanyFactsIntakeError("one Company Facts source manifest is referenced by multiple attempts")
        referenced_sources.add(source_manifest_id)
        source_content = source["content"]
        source_cik = source["issuer"]["cik"]
        if (
            source_cik != cik
            or source["anchor"]["capital_structure_manifest_id"] != record["anchor_manifest_id"]
            or result["content_sha256"] != source_content["content_sha256"]
            or int(result["byte_length"]) != int(source_content["byte_length"])
        ):
            raise CompanyFactsIntakeError("coverage result/source manifest referential binding mismatch")
        if attempted_at > _parse_stamp(source["retrieval"]["first_seen_at"], field="source first_seen_at"):
            raise CompanyFactsIntakeError("coverage/source clocks violate acquisition causality")
    orphan_sources = set(sources_by_id) - referenced_sources
    if orphan_sources:
        raise CompanyFactsIntakeError("unreferenced Company Facts source manifests are not admissible")


def _retention_audit_plan(
    source_records: Sequence[Mapping[str, Any]], *, selection_as_of: datetime,
    max_objects: int = MAX_RETENTION_VERIFY_OBJECTS,
) -> list[tuple[dict[str, Any], str]]:
    """Pick a deterministic, bounded 2:1 latest-to-history retention sample.

    The date-keyed cursor means no-op days advance the historical audit without
    inflating the immutable receipt chain.  A newer admission is not included
    here: its source-store ``put_verified`` performs the stronger exact check.
    """
    if isinstance(max_objects, bool) or not isinstance(max_objects, int) or max_objects < 0:
        raise ValueError("retention audit max_objects must be a non-negative integer")
    normalized = [_native(raw) for raw in source_records]
    by_cik: dict[str, list[dict[str, Any]]] = {}
    for record in normalized:
        issuer = record.get("issuer") if isinstance(record.get("issuer"), Mapping) else {}
        cik = canonical_cik(issuer.get("cik"))
        if cik is None:
            raise CompanyFactsIntakeError("Company Facts retention audit source has no canonical CIK")
        by_cik.setdefault(cik, []).append(record)
    latest: list[dict[str, Any]] = []
    historical: list[dict[str, Any]] = []
    for cik in sorted(by_cik):
        records = sorted(
            by_cik[cik],
            key=lambda row: (
                _parse_stamp(row["retrieval"]["first_seen_at"], field="source first_seen_at"),
                str(row["manifest_id"]),
            ),
        )
        latest.append(records[-1])
        historical.extend(records[:-1])
    historical.sort(key=lambda row: (
        _parse_stamp(row["retrieval"]["first_seen_at"], field="source first_seen_at"),
        str(row["manifest_id"]),
    ))
    lanes = {"current": latest, "historical": historical}
    positions = {
        name: selection_as_of.date().toordinal() % len(rows) if rows else 0
        for name, rows in lanes.items()
    }
    cursor = selection_as_of.date().toordinal() % len(_RETENTION_VERIFY_SCHEDULE)
    selected: list[tuple[dict[str, Any], str]] = []
    ceiling = min(max_objects, len(normalized))
    while len(selected) < ceiling and any(lanes.values()):
        chosen: str | None = None
        for offset in range(len(_RETENTION_VERIFY_SCHEDULE)):
            candidate = _RETENTION_VERIFY_SCHEDULE[(cursor + offset) % len(_RETENTION_VERIFY_SCHEDULE)]
            if lanes[candidate]:
                chosen = candidate
                cursor = (cursor + offset + 1) % len(_RETENTION_VERIFY_SCHEDULE)
                break
        if chosen is None:
            break
        rows = lanes[chosen]
        position = positions[chosen] % len(rows)
        selected.append((rows.pop(position), chosen))
        if rows:
            positions[chosen] = position % len(rows)
    return selected


def _retention_verification(
    prior_source_records: Sequence[Mapping[str, Any]], *, selection_as_of: datetime,
    admitted_source_records: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Honest coverage metadata: ``sampled`` never means all history was reread."""
    plan = _retention_audit_plan(prior_source_records, selection_as_of=selection_as_of)
    current_ids = [str(record["manifest_id"]) for record, lane in plan if lane == "current"]
    historical_ids = [str(record["manifest_id"]) for record, lane in plan if lane == "historical"]
    admitted_ids = [str(_native(record)["manifest_id"]) for record in admitted_source_records]
    verified_ids = [*current_ids, *historical_ids, *admitted_ids]
    if len(set(verified_ids)) != len(verified_ids):
        raise CompanyFactsIntakeError("Company Facts retention verification has duplicate manifest identities")
    eligible = len(prior_source_records) + len(admitted_source_records)
    all_objects_reverified = len(verified_ids) == eligible
    return {
        "policy": RETENTION_VERIFY_POLICY,
        "selection_day": selection_as_of.date().isoformat(),
        "eligible_objects": eligible,
        "latest_objects": len({
            canonical_cik((_native(row).get("issuer") or {}).get("cik")) for row in [*prior_source_records, *admitted_source_records]
        }),
        "historical_objects": max(0, eligible - len({
            canonical_cik((_native(row).get("issuer") or {}).get("cik")) for row in [*prior_source_records, *admitted_source_records]
        })),
        "checked_current_manifest_ids": current_ids,
        "checked_historical_manifest_ids": historical_ids,
        "admission_verified_manifest_ids": admitted_ids,
        "verified_manifest_ids": verified_ids,
        "all_objects_reverified": all_objects_reverified,
        "freshness": "complete" if all_objects_reverified else "sampled",
    }


def _get_verified_before_deadline(
    store: Any, object_key: object, content_sha256: object, *, deadline: float | None,
    monotonic: Callable[[], float],
) -> Any:
    """Bound one uncooperative store read without allowing it to consume the run.

    Content stores expose no universal per-call timeout.  The read is therefore
    isolated in a daemon thread; it has no write authority and its late result is
    discarded.  The caller returns at the hard remaining-wallclock boundary.
    """
    if deadline is None:
        return store.get_verified(object_key, content_sha256)
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise CompanyFactsRunBudgetExceeded("Company Facts retention verification exceeded run deadline")
    completed = threading.Event()
    result: dict[str, Any] = {}

    def read() -> None:
        try:
            result["body"] = store.get_verified(object_key, content_sha256)
        except BaseException as exc:  # noqa: BLE001 - forwarded into fail-closed caller
            result["error"] = exc
        finally:
            completed.set()

    threading.Thread(target=read, name="companyfacts-retention-read", daemon=True).start()
    if not completed.wait(remaining):
        raise CompanyFactsRunBudgetExceeded("Company Facts retention verification read exceeded remaining run deadline")
    if monotonic() > deadline:
        raise CompanyFactsRunBudgetExceeded("Company Facts retention verification exceeded run deadline")
    error = result.get("error")
    if isinstance(error, BaseException):
        raise error
    return result.get("body")


def _verify_selected_source_objects(
    source_records: Sequence[Mapping[str, Any]], *, source_stores: Mapping[str, Any],
    deadline: float | None = None, monotonic: Callable[[], float] = time.monotonic,
) -> None:
    """Require each *selected* retained source object to remain exact and readable."""
    for raw in source_records:
        source = _native(raw)
        storage = source.get("storage") if isinstance(source.get("storage"), Mapping) else {}
        content = source.get("content") if isinstance(source.get("content"), Mapping) else {}
        store_id = storage.get("store_id")
        store = source_stores.get(store_id) if isinstance(store_id, str) else None
        if store is None:
            raise CompanyFactsIntakeError(
                f"Company Facts selected source store is unavailable: {store_id!r}"
            )
        if getattr(store, "backend", None) != storage.get("backend"):
            raise CompanyFactsIntakeError("Company Facts selected source store backend is detached")
        try:
            body = _get_verified_before_deadline(
                store, storage.get("object_key"), content.get("content_sha256"),
                deadline=deadline, monotonic=monotonic,
            )
        except CompanyFactsRunBudgetExceeded:
            raise
        except Exception as exc:  # noqa: BLE001
            raise CompanyFactsIntakeError("Company Facts selected source object verification failed") from exc
        if body is None or len(body) != int(content.get("byte_length") or -1):
            raise CompanyFactsIntakeError("Company Facts selected source object is missing or mismatched")


def _validate_generation_identity(receipt: Mapping[str, Any]) -> None:
    descriptor = receipt.get("generation")
    if not isinstance(descriptor, Mapping):
        raise CompanyFactsIntakeError("Company Facts receipt has no generation descriptor")
    source = descriptor.get("source_manifest")
    coverage = descriptor.get("coverage")
    if not isinstance(source, Mapping) or not isinstance(coverage, Mapping):
        raise CompanyFactsIntakeError("Company Facts generation file descriptors are invalid")
    expected = _generation_id(
        source_file={"sha256": source.get("sha256"), "byte_length": source.get("byte_length")},
        coverage_file={"sha256": coverage.get("sha256"), "byte_length": coverage.get("byte_length")},
        source_ledger=receipt["companyfacts_manifest_ledger"],
        coverage_ledger=receipt["coverage_ledger"],
    )
    actual = descriptor.get("generation_id")
    if not isinstance(actual, str) or not hmac.compare_digest(actual, expected):
        raise CompanyFactsIntakeError("Company Facts generation identity does not bind files and ledgers")


def _receipt_reference(receipt: Mapping[str, Any], path: Path, *, root: Path) -> dict[str, Any]:
    relative = path.parent.name + "/" + path.name
    return {"receipt_id": receipt["receipt_id"], "path": relative, **_file_receipt(path, root=root)}


def _read_receipt_reference(
    root: Path, reference: Mapping[str, Any], *, signer: CompanyFactsSigner,
) -> dict[str, Any]:
    receipt_id = str(reference.get("receipt_id") or "")
    digest = receipt_id.removeprefix("receipt:cs-companyfacts:")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise CompanyFactsIntakeError("invalid immutable Company Facts receipt identity")
    expected_relative = f"receipts/{digest}.json"
    if reference.get("path") != expected_relative:
        raise CompanyFactsIntakeError("immutable Company Facts receipt path is not identity-bound")
    path = root / expected_relative
    expected_file = {
        "sha256": reference.get("sha256"), "byte_length": reference.get("byte_length")
    }
    if _file_receipt(path, root=root) != expected_file:
        raise CompanyFactsIntakeError("immutable Company Facts receipt exact-byte mismatch")
    parts = _relative_parts(root, path)
    with _open_companyfacts_parent(root, parts) as (parent_fd, name):
        body = _read_regular_bytes_at(parent_fd, name, label="immutable receipt")
        assert body is not None
    try:
        receipt = _native(json.loads(body))
    except Exception as exc:  # noqa: BLE001
        raise CompanyFactsIntakeError("immutable Company Facts receipt is unreadable") from exc
    if not isinstance(receipt, Mapping) or body != _canonical_bytes(receipt) + b"\n":
        raise CompanyFactsIntakeError("immutable Company Facts receipt bytes are not canonical")
    _validate_contract(
        receipt, "capital_structure_companyfacts_coverage_receipt.schema.json",
        label="immutable Company Facts receipt",
    )
    _validate_receipt_identity(receipt)
    _validate_receipt_authentication(receipt, signer=signer)
    _validate_generation_identity(receipt)
    if receipt["receipt_id"] != receipt_id:
        raise CompanyFactsIntakeError("immutable receipt reference/receipt_id mismatch")
    _validate_generation_files(root, receipt["generation"])
    return dict(receipt)


def _load_receipt_generation(
    root: Path, receipt: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Authenticate one receipt's exact immutable generation and commitments."""
    source_body, coverage_body = _generation_bodies(root, receipt["generation"])
    source_records = _records(_read_ledger_bytes(source_body, _SOURCE_MANIFEST_COLUMNS, label="committed source manifest"))
    coverage_records = _records(_read_ledger_bytes(coverage_body, _COVERAGE_COLUMNS, label="committed coverage"))
    if _ledger_receipt(source_records) != receipt["companyfacts_manifest_ledger"]:
        raise CompanyFactsIntakeError("receipt/source manifest ordered-prefix mismatch")
    if _ledger_receipt(coverage_records) != receipt["coverage_ledger"]:
        raise CompanyFactsIntakeError("receipt/coverage ordered-prefix mismatch")
    return source_records, coverage_records


def _walk_receipt_chain(
    root: Path, current_reference: Mapping[str, Any], *, signer: CompanyFactsSigner,
) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    reference: Mapping[str, Any] | None = current_reference
    while reference is not None:
        if len(chain) >= MAX_RECEIPT_CHAIN_LENGTH:
            raise CompanyFactsIntakeError(
                "Company Facts receipt chain reached its hard checkpoint/compaction boundary"
            )
        receipt = _read_receipt_reference(root, reference, signer=signer)
        receipt_id = str(receipt["receipt_id"])
        if receipt_id in seen:
            raise CompanyFactsIntakeError("Company Facts receipt chain contains a cycle")
        seen.add(receipt_id)
        if chain:
            child = chain[-1]
            if int(child["sequence"]) != int(receipt["sequence"]) + 1:
                raise CompanyFactsIntakeError("Company Facts receipt sequence is not contiguous")
            if _parse_stamp(receipt["published_at"], field="prior published_at") > _parse_stamp(
                child["selection_as_of"], field="child selection_as_of"
            ):
                raise CompanyFactsIntakeError("Company Facts receipt chain clocks overlap")
        chain.append(receipt)
        previous = receipt.get("previous_receipt")
        reference = previous if isinstance(previous, Mapping) else None
    if not chain or int(chain[-1]["sequence"]) != 1 or chain[-1].get("previous_receipt") is not None:
        raise CompanyFactsIntakeError("Company Facts receipt chain has no valid genesis")
    return chain


def _assert_receipt_chain_prefixes(
    chain: Sequence[Mapping[str, Any]], *, anchor_records: Sequence[Mapping[str, Any]],
    source_records: Sequence[Mapping[str, Any]], coverage_records: Sequence[Mapping[str, Any]],
) -> None:
    for receipt in chain:
        commitments = (
            ("anchor_manifest_ledger", anchor_records),
            ("companyfacts_manifest_ledger", source_records),
            ("coverage_ledger", coverage_records),
        )
        for field, records in commitments:
            expected = receipt[field]
            count = int(expected["record_count"])
            if len(records) < count or _ledger_receipt(records[:count]) != expected:
                raise CompanyFactsIntakeError(f"receipt chain {field} is not an ordered prefix")


def _load_committed_bundle(
    *, root: Path, receipt_path: Path, anchor_records: Sequence[Mapping[str, Any]],
    signer: CompanyFactsSigner | None = None, head_witness: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    """Load only the generation selected by an authenticated immutable receipt chain."""
    try:
        with _open_companyfacts_directory(root) as root_fd:
            names = set(os.listdir(root_fd))
            immutable_history = any(name in names for name in ("receipts", "generations")) or any(
                name.startswith(".generation-stage-") for name in names
            )
            pointer_parts = _relative_parts(root, receipt_path)
            with _open_companyfacts_parent(root, pointer_parts) as (parent_fd, pointer_name):
                pointer_body = _read_regular_bytes_at(
                    parent_fd, pointer_name, label="current pointer", missing_ok=True,
                )
    except CompanyFactsPathMissing:
        # A securely proven missing root is an empty bootstrap. Unsafe ancestors
        # and symlinks raise a different error and remain fatal.
        immutable_history = False
        pointer_body = None
        names = set()
    if pointer_body is None:
        if {"source_manifest.parquet", "coverage.parquet"} & names or immutable_history or head_witness is not None:
            raise CompanyFactsIntakeError(
                "missing Company Facts current pointer with immutable history requires explicit recovery"
            )
        return [], [], None
    if signer is None:
        raise CompanyFactsIntakeError("Company Facts startup requires an authenticated receipt signer")
    if head_witness is None:
        raise CompanyFactsIntakeError("Company Facts startup requires an external authenticated head witness")
    try:
        pointer = _native(json.loads(pointer_body))
    except Exception as exc:  # noqa: BLE001
        raise CompanyFactsIntakeError("unreadable Company Facts current pointer") from exc
    if not isinstance(pointer, Mapping) or pointer_body != _canonical_bytes(pointer) + b"\n":
        raise CompanyFactsIntakeError("Company Facts current pointer bytes are not canonical")
    _validate_contract(
        pointer, "capital_structure_companyfacts_current_pointer.schema.json",
        label="Company Facts current pointer",
    )
    _validate_pointer_identity(pointer)
    current_reference = {
        "receipt_id": pointer["receipt_id"], "path": pointer["receipt_path"],
        "sha256": pointer["receipt_sha256"], "byte_length": pointer["receipt_byte_length"],
    }
    chain = _walk_receipt_chain(root, current_reference, signer=signer)
    receipt = chain[0]
    if (
        pointer["generation_id"] != receipt["generation"]["generation_id"]
        or pointer["published_at"] != receipt["published_at"]
    ):
        raise CompanyFactsIntakeError("Company Facts pointer is detached from immutable receipt")
    _validate_head_witness(head_witness, signer=signer)
    head_file = _file_receipt(root / str(pointer["receipt_path"]), root=root)
    head_previous = receipt.get("previous_receipt")
    expected_head = {
        "sequence": int(receipt["sequence"]),
        "receipt_id": receipt["receipt_id"],
        "receipt_sha256": head_file["sha256"],
        "receipt_byte_length": head_file["byte_length"],
        "generation_id": receipt["generation"]["generation_id"],
        "published_at": receipt["published_at"],
        "previous_receipt_id": head_previous.get("receipt_id") if isinstance(head_previous, Mapping) else None,
    }
    if any(head_witness[field] != value for field, value in expected_head.items()):
        raise CompanyFactsIntakeError("Company Facts local pointer is not the externally witnessed head")
    generations: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]] = {}
    prior_sources: list[dict[str, Any]] = []
    prior_coverage: list[dict[str, Any]] = []
    for chained_receipt in reversed(chain):
        chained_sources, chained_coverage = _load_receipt_generation(root, chained_receipt)
        anchor_count = int(chained_receipt["anchor_manifest_ledger"]["record_count"])
        if anchor_count > len(anchor_records):
            raise CompanyFactsIntakeError("receipt chain requires unavailable filing-anchor prefix")
        _validate_companyfacts_bundle(
            anchor_records=anchor_records[:anchor_count], source_records=chained_sources,
            coverage_records=chained_coverage,
        )
        _validate_receipt_semantics(
            chained_receipt, anchor_records=anchor_records[:anchor_count],
            source_records=chained_sources, coverage_records=chained_coverage,
            prior_source_records=prior_sources, prior_coverage_records=prior_coverage,
        )
        generations[str(chained_receipt["receipt_id"])] = (chained_sources, chained_coverage)
        prior_sources, prior_coverage = chained_sources, chained_coverage
    source_records, coverage_records = generations[str(receipt["receipt_id"])]
    _assert_receipt_chain_prefixes(
        chain, anchor_records=anchor_records, source_records=source_records,
        coverage_records=coverage_records,
    )
    return source_records, coverage_records, receipt


def _latest_coverage(records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for raw in records:
        record = _native(raw)
        _validate_contract(record, "capital_structure_companyfacts_coverage_row.schema.json", label="coverage row")
        _validate_coverage_identity(record)
        cik = str(record["cik"])
        rank = (
            int(record["attempt_count"]),
            _parse_stamp(record["attempted_at"], field="coverage attempted_at"),
            str(record["coverage_id"]),
        )
        prior = latest.get(cik)
        prior_rank = None if prior is None else (
            int(prior["attempt_count"]),
            _parse_stamp(prior["attempted_at"], field="coverage attempted_at"),
            str(prior["coverage_id"]),
        )
        if prior_rank is None or rank > prior_rank:
            latest[cik] = record
    return latest


def select_companyfacts_queue(
    anchors: Mapping[str, Mapping[str, Any]],
    coverage_records: Sequence[Mapping[str, Any]],
    *, now: datetime,
    max_ciks: int,
    force_refresh: bool = False,
    cursor_sequence: int = 0,
    diagnostics: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], int, int]:
    """Return bounded work with deterministic retry/new/refresh progress.

    The two non-selected counters are deliberately separate: a still-fresh
    retrieved response is not backlog, while a retry/defer clock or the hard
    per-run cap is a visible deferred work item. A rotating 2:1:1 schedule
    prevents any non-empty lane from being starved, even when ``max_ciks`` is 1.
    """
    if isinstance(max_ciks, bool) or not isinstance(max_ciks, int) or not 0 <= max_ciks <= HARD_MAX_CIKS_PER_RUN:
        raise ValueError(f"max_ciks must be an integer from 0 to {HARD_MAX_CIKS_PER_RUN}")
    stamp = _parse_stamp(now, field="queue now")
    latest = _latest_coverage(coverage_records)
    lanes: dict[str, list[dict[str, Any]]] = {
        "retry_due": [], "new_anchor": [], "refresh_due": [],
    }
    deferred = 0
    skipped_fresh = 0
    for cik in sorted(anchors):
        anchor = dict(anchors[cik])
        prior = latest.get(cik)
        reason: str | None = None
        due_at = anchor["first_seen_at"]
        if prior is None:
            reason = "new_anchor"
        elif prior["state"] in {"retry", "deferred"}:
            retry_after = _parse_stamp(prior["retry_after"], field="coverage retry_after")
            if retry_after <= stamp:
                reason, due_at = "retry_due", retry_after
            else:
                deferred += 1
        elif prior["state"] == "retrieved":
            attempted = _parse_stamp(prior["attempted_at"], field="coverage attempted_at")
            if force_refresh or attempted + REFRESH_AFTER <= stamp:
                reason, due_at = "refresh_due", attempted + REFRESH_AFTER
            else:
                skipped_fresh += 1
        else:  # Contract excludes this, preserve a fail-closed queue.
            raise CompanyFactsIntakeError(f"unknown coverage state for {cik}")
        if reason:
            lanes[reason].append({
                "cik": cik,
                "anchor": anchor,
                "queue_reason": reason,
                "attempt_count": int(prior["attempt_count"]) + 1 if prior else 1,
                "due_at": _parse_stamp(due_at, field=f"{reason} due_at"),
            })
    for rows in lanes.values():
        rows.sort(key=lambda item: (item["due_at"], item["cik"]))
    due_by_reason = {reason: len(rows) for reason, rows in lanes.items()}
    selected: list[dict[str, Any]] = []
    if isinstance(cursor_sequence, bool) or not isinstance(cursor_sequence, int) or cursor_sequence < 0:
        raise ValueError("queue cursor_sequence must be a non-negative integer")
    # The committed receipt sequence, rather than calendar date, advances the
    # weighted round robin across manual/retry runs on the same day.
    cursor = cursor_sequence % len(_QUEUE_SCHEDULE)
    while len(selected) < max_ciks and any(lanes.values()):
        chosen_index: int | None = None
        for offset in range(len(_QUEUE_SCHEDULE)):
            index = (cursor + offset) % len(_QUEUE_SCHEDULE)
            if lanes[_QUEUE_SCHEDULE[index]]:
                chosen_index = index
                break
        if chosen_index is None:
            break
        reason = _QUEUE_SCHEDULE[chosen_index]
        item = lanes[reason].pop(0)
        item.pop("due_at", None)
        selected.append(item)
        cursor = (chosen_index + 1) % len(_QUEUE_SCHEDULE)
    total_due = sum(due_by_reason.values())
    deferred += max(0, total_due - len(selected))
    selected_by_reason = {
        reason: sum(item["queue_reason"] == reason for item in selected)
        for reason in lanes
    }
    if diagnostics is not None:
        diagnostics.clear()
        diagnostics.update({
            "due_by_reason": due_by_reason,
            "selected_by_reason": selected_by_reason,
            "cursor_sequence": cursor_sequence,
            "force_refresh": force_refresh,
        })
    return selected, deferred, skipped_fresh


def _response_content_length(headers: Any, *, url: str, limit: int) -> None:
    if not isinstance(headers, Mapping):
        return
    declared = headers.get("Content-Length", headers.get("content-length"))
    if declared is None:
        return
    try:
        value = int(str(declared).strip())
    except (TypeError, ValueError):
        return
    if value < 0 or value > limit:
        raise CompanyFactsResponseTooLarge(f"SEC Company Facts response exceeds bounded ingest limit for {url}")


def _retry_after_seconds(headers: Any, *, now: datetime) -> float | None:
    if not isinstance(headers, Mapping):
        return None
    raw = headers.get("Retry-After", headers.get("retry-after"))
    if raw is None:
        return None
    rendered = str(raw).strip()
    try:
        seconds = float(rendered)
    except ValueError:
        try:
            target = parsedate_to_datetime(rendered)
            target = _strict_utc(target, field="Retry-After HTTP date")
            seconds = (target - _strict_utc(now, field="Retry-After now")).total_seconds()
        except Exception:  # noqa: BLE001
            return None
    if not math.isfinite(seconds):
        return None
    return max(0.0, seconds)


def stream_companyfacts_response(
    response: Any, *, cik: str, url: str, limit: int,
    deadline: float | None = None, monotonic: Callable[[], float] = time.monotonic,
    byte_observer: Callable[[int], None] | None = None,
) -> bytes:
    """Read a single response with cap enforcement before JSON/CIK admission."""
    _response_content_length(getattr(response, "headers", {}), url=url, limit=limit)
    iterator = getattr(response, "iter_content", None)
    if not callable(iterator):
        raise CompanyFactsIntakeError("SEC response does not support bounded iter_content")
    chunks: list[bytes] = []
    total = 0
    for chunk in iterator(chunk_size=64 * 1024):
        if deadline is not None and monotonic() >= deadline:
            raise CompanyFactsRunBudgetExceeded("SEC Company Facts response exceeded run deadline")
        if not isinstance(chunk, bytes):
            raise CompanyFactsIntakeError("SEC response stream yielded non-bytes")
        if not chunk:
            continue
        total += len(chunk)
        if byte_observer is not None:
            byte_observer(len(chunk))
        if total > limit:
            raise CompanyFactsResponseTooLarge(f"SEC Company Facts response exceeds bounded ingest limit for {url}")
        chunks.append(chunk)
    raw = b"".join(chunks)
    if not raw:
        raise CompanyFactsDeferred("SEC Company Facts response is empty")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompanyFactsDeferred("SEC Company Facts response is not UTF-8 JSON") from exc
    if not isinstance(payload, Mapping) or canonical_cik(payload.get("cik")) != cik:
        raise CompanyFactsDeferred("SEC Company Facts JSON CIK does not match requested CIK")
    if not isinstance(payload.get("facts"), Mapping):
        raise CompanyFactsDeferred("SEC Company Facts JSON has no facts object")
    return raw


def _response_error_class(exc: Exception, *, attempted_at: datetime) -> tuple[str, datetime]:
    if isinstance(exc, CompanyFactsRetryable):
        return "retry", _strict_utc(exc.retry_after_at or attempted_at + RETRY_AFTER, field="retry_after")
    if isinstance(exc, CompanyFactsRunBudgetExceeded) and exc.retry_after_at is not None:
        return "retry", _strict_utc(exc.retry_after_at, field="retry_after")
    if isinstance(exc, (CompanyFactsResponseTooLarge, CompanyFactsDeferred, ValueError)):
        return "deferred", attempted_at + DEFER_AFTER
    return "retry", attempted_at + RETRY_AFTER


class SecCapitalStructureCompanyFactsAdapter(Adapter):
    """Fetch bounded, anchored SEC Company Facts source evidence only."""

    name = "sec_capital_structure_companyfacts"
    group = GROUP
    stale_after_days = 4

    def __init__(
        self,
        *,
        source_store=None,
        source_stores: Mapping[str, Any] | None = None,
        signer: CompanyFactsSigner | None = None,
        head_guard: CompanyFactsHeadGuard | None = None,
        now_fn: Callable[[], datetime] = _utc_now,
        fetcher: Callable[..., Any] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        max_ciks_per_run: int = MAX_CIKS_PER_RUN,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        max_run_bytes: int = MAX_RUN_BYTES,
        max_run_seconds: float = MAX_RUN_SECONDS,
    ) -> None:
        self._injected_source_store = source_store
        self._injected_source_stores = dict(source_stores) if source_stores is not None else None
        if (signer is None) != (head_guard is None):
            raise ValueError("Company Facts signer and head_guard must be supplied together")
        self._injected_signer = signer
        self._injected_head_guard = head_guard
        self._now_fn = now_fn
        self._fetcher = fetcher or requests.get
        self._sleep = sleeper
        self._monotonic = monotonic
        self._last_request_at: float | None = None
        self._cooldown_until: float | None = None
        self._run_deadline: float | None = None
        self._run_bytes = 0
        if isinstance(max_ciks_per_run, bool) or not isinstance(max_ciks_per_run, int):
            raise ValueError(f"max_ciks_per_run must be an integer from 0 to {HARD_MAX_CIKS_PER_RUN}")
        if isinstance(max_response_bytes, bool) or not isinstance(max_response_bytes, int):
            raise ValueError(f"max_response_bytes must be an integer from 1 to {HARD_MAX_RESPONSE_BYTES}")
        if isinstance(max_run_bytes, bool) or not isinstance(max_run_bytes, int):
            raise ValueError(f"max_run_bytes must be an integer from 1 to {HARD_MAX_RUN_BYTES}")
        if isinstance(max_run_seconds, bool) or not isinstance(max_run_seconds, (int, float)):
            raise ValueError(f"max_run_seconds must be a finite number from 1 to {HARD_MAX_RUN_SECONDS}")
        self.max_ciks_per_run = max_ciks_per_run
        self.max_response_bytes = max_response_bytes
        self.max_run_bytes = max_run_bytes
        self.max_run_seconds = float(max_run_seconds)
        if not 0 <= self.max_ciks_per_run <= HARD_MAX_CIKS_PER_RUN:
            raise ValueError(f"max_ciks_per_run must be from 0 to {HARD_MAX_CIKS_PER_RUN}")
        if not 1 <= self.max_response_bytes <= HARD_MAX_RESPONSE_BYTES:
            raise ValueError(f"max_response_bytes must be from 1 to {HARD_MAX_RESPONSE_BYTES}")
        if not 1 <= self.max_run_bytes <= HARD_MAX_RUN_BYTES:
            raise ValueError(f"max_run_bytes must be from 1 to {HARD_MAX_RUN_BYTES}")
        if not math.isfinite(self.max_run_seconds) or not 1 <= self.max_run_seconds <= HARD_MAX_RUN_SECONDS:
            raise ValueError(f"max_run_seconds must be from 1 to {HARD_MAX_RUN_SECONDS}")

    def _source_store(self):
        if self._injected_source_store is not None:
            return self._injected_source_store
        from engine.capital_structure.source_store import build_source_store

        return build_source_store()

    def _source_stores(self) -> dict[str, Any]:
        if self._injected_source_stores is not None:
            return dict(self._injected_source_stores)
        if self._injected_source_store is not None:
            store_id = getattr(self._injected_source_store, "store_id", None)
            if isinstance(store_id, str):
                return {store_id: self._injected_source_store}
            return {}
        from engine.capital_structure.source_store import build_source_stores

        return build_source_stores()

    def _trust_context(self) -> tuple[CompanyFactsSigner, CompanyFactsHeadGuard]:
        if self._injected_signer is not None and self._injected_head_guard is not None:
            return self._injected_signer, self._injected_head_guard
        return _build_production_trust_context()

    def fetch_result_status(self, frames: dict[str, pd.DataFrame]) -> str | None:
        heartbeat = frames.get("sec_companyfacts_intake")
        if heartbeat is not None and not heartbeat.empty and str(heartbeat.iloc[-1].get("status")) == "checkpoint_blocked":
            # A checkpoint migration is an explicit operator dependency, not an
            # upstream failure.  Tell the generic breaker to remain healthy.
            return "blocked"
        return None

    def _pace(self) -> None:
        while True:
            now = self._monotonic()
            delay = 0.0
            if self._last_request_at is not None:
                delay = max(delay, PACE_SECONDS - (now - self._last_request_at))
            if self._cooldown_until is not None:
                delay = max(delay, self._cooldown_until - now)
            if delay <= 0:
                if self._cooldown_until is not None and now >= self._cooldown_until:
                    self._cooldown_until = None
                return
            if self._run_deadline is not None and now + delay >= self._run_deadline:
                raise CompanyFactsRunBudgetExceeded("SEC cooldown exceeds Company Facts run deadline")
            self._sleep(delay)
            if self._monotonic() <= now:
                raise CompanyFactsRunBudgetExceeded("SEC cooldown sleep did not advance the run clock")

    def _extend_global_cooldown(self, seconds: float) -> None:
        if seconds <= 0:
            return
        target = self._monotonic() + seconds
        self._cooldown_until = max(self._cooldown_until or target, target)

    def _remaining_run_seconds(self) -> float:
        if self._run_deadline is None:
            return self.max_run_seconds
        return self._run_deadline - self._monotonic()

    def _require_run_time(self) -> None:
        if self._remaining_run_seconds() <= 0:
            raise CompanyFactsRunBudgetExceeded("Company Facts run wall-clock budget exhausted")

    def _require_run_budget(self) -> None:
        self._require_run_time()
        if self._run_bytes >= self.max_run_bytes:
            raise CompanyFactsRunBudgetExceeded("Company Facts run byte budget exhausted")

    def _consume_run_bytes(self, count: int) -> None:
        if not isinstance(count, int) or count < 0:
            raise CompanyFactsIntakeError("Company Facts stream reported invalid byte count")
        self._run_bytes += count
        if self._run_bytes > self.max_run_bytes:
            raise CompanyFactsRunBudgetExceeded("Company Facts run byte budget exhausted")

    @staticmethod
    def _close(response: Any) -> None:
        closer = getattr(response, "close", None)
        if callable(closer):
            try:
                closer()
            except Exception:  # noqa: BLE001
                pass

    def _fetch_companyfacts(self, cik: str) -> bytes:
        url = companyfacts_url(cik)
        headers = {"User-Agent": _ua(), "Accept-Encoding": "gzip, deflate"}
        last_error: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            response = None
            retry_after: float | None = None
            try:
                self._require_run_budget()
                self._pace()
                remaining_seconds = self._remaining_run_seconds()
                if remaining_seconds <= 0:
                    raise CompanyFactsRunBudgetExceeded("Company Facts run wall-clock budget exhausted")
                response = self._fetcher(
                    url, headers=headers,
                    timeout=(max(0.001, min(15.0, remaining_seconds)), max(0.001, min(45.0, remaining_seconds))),
                    stream=True,
                )
                self._last_request_at = self._monotonic()
                status = getattr(response, "status_code", None)
                if not isinstance(status, int):
                    raise CompanyFactsIntakeError("SEC response has no integer HTTP status")
                if status in {429, 500, 502, 503, 504}:
                    observed_at = _strict_utc(self._now_fn(), field="Retry-After observation clock")
                    retry_after = _retry_after_seconds(
                        getattr(response, "headers", {}),
                        now=observed_at,
                    )
                    self._extend_global_cooldown(retry_after or 0.0)
                    retry_at = observed_at + timedelta(seconds=retry_after) if retry_after is not None else None
                    raise CompanyFactsRetryable(f"HTTP {status}", retry_after_at=retry_at)
                if status != 200:
                    raise CompanyFactsDeferred(f"SEC Company Facts HTTP {status}")
                return stream_companyfacts_response(
                    response, cik=cik, url=url,
                    limit=min(self.max_response_bytes, self.max_run_bytes - self._run_bytes),
                    deadline=self._run_deadline, monotonic=self._monotonic,
                    byte_observer=self._consume_run_bytes,
                )
            except (CompanyFactsDeferred, CompanyFactsResponseTooLarge):
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt + 1 >= MAX_ATTEMPTS or not (
                    is_connection_error(exc)
                    or isinstance(exc, requests.RequestException)
                    or isinstance(exc, CompanyFactsRetryable)
                ):
                    raise
                delay = max(float(2 ** attempt), retry_after or 0.0)
                if self._remaining_run_seconds() <= delay:
                    raise CompanyFactsRunBudgetExceeded(
                        "SEC retry cooldown exceeds Company Facts run deadline",
                        retry_after_at=getattr(exc, "retry_after_at", None),
                    ) from exc
                self._extend_global_cooldown(delay)
            finally:
                if response is not None:
                    self._close(response)
        raise last_error or CompanyFactsIntakeError("Company Facts fetch failed")

    @staticmethod
    def _source_manifest(*, cik: str, anchor: Mapping[str, Any], raw: bytes, receipt: Any, retained_at: str) -> dict[str, Any]:
        digest = sha256(raw).hexdigest()
        if (
            getattr(receipt, "sha256", None) != digest
            or getattr(receipt, "byte_length", None) != len(raw)
            or getattr(receipt, "object_key", None) != object_key_for_sha256(digest)
            or getattr(receipt, "media_type", None) != "application/json"
        ):
            raise CompanyFactsIntakeError("source-store receipt does not bind exact Company Facts bytes")
        ticker = anchor.get("ticker") if isinstance(anchor.get("ticker"), str) else None
        aliases = [str(value) for value in anchor.get("aliases", []) if str(value)]
        record: dict[str, Any] = {
            "schema": SOURCE_MANIFEST_SCHEMA,
            "source_system": "sec_edgar_companyfacts",
            "source_id": f"sec-companyfacts:{cik}:{digest}",
            "issuer": {"issuer_id": f"sec:cik:{cik}", "cik": cik, "ticker": ticker, "aliases": sorted(set(aliases))},
            "anchor": {
                "capital_structure_manifest_id": anchor["manifest_id"],
                "capital_structure_source_id": anchor["source_id"],
                "complete_submission_sha256": anchor["content_sha256"],
                "complete_submission_byte_length": int(anchor["byte_length"]),
                "complete_submission_backend": anchor["storage_backend"],
                "complete_submission_store_id": anchor["storage_store_id"],
                "complete_submission_object_key": anchor["storage_object_key"],
                "first_seen_at": _iso(anchor["first_seen_at"]),
            },
            "request": {"canonical_url": companyfacts_url(cik), "endpoint": "companyfacts", "method": "GET"},
            "retrieval": {"retrieved_at": retained_at, "first_seen_at": retained_at, "transport_status": "retrieved"},
            "content": {"media_type": "application/json", "byte_length": len(raw), "content_sha256": digest, "root_locator": f"sha256:{digest}"},
            "storage": {"backend": receipt.backend, "store_id": receipt.store_id, "object_key": receipt.object_key, "content_addressed": True, "retention_state": "retained"},
            "rights": {"redistribution_class": "public_source_link", "attribution_required": True, "license_note": "United States SEC EDGAR public Company Facts response"},
            "privacy": {"classification": "public", "contains_personal_data": False},
            "parser": {"eligibility": "eligible", "corruption_state": "clean", "parser_version": "companyfacts-json-cik-validator/1.0.0"},
            "spans": [{"span_id": f"root:{digest}", "locator_type": "document", "locator": f"bytes:0-{len(raw)}", "text_sha256": digest}],
            "authority": _authority(),
        }
        record["manifest_id"] = _source_manifest_id(record)
        _validate_contract(record, "capital_structure_companyfacts_source_manifest.schema.json", label="Company Facts source manifest")
        _validate_source_manifest_identity(record)
        return record

    @staticmethod
    def _coverage_row(
        *, item: Mapping[str, Any], attempted_at: str, state: str, error: str | None, retry_after: str | None,
        manifest: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        content = manifest.get("content") if isinstance(manifest, Mapping) else None
        record: dict[str, Any] = {
            "schema": COVERAGE_ROW_SCHEMA,
            "cik": item["cik"],
            "anchor_manifest_id": item["anchor"]["manifest_id"],
            "anchor_first_seen_at": _iso(item["anchor"]["first_seen_at"]),
            "attempted_at": attempted_at,
            "attempt_count": item["attempt_count"],
            "queue_reason": item["queue_reason"],
            "state": state,
            "retry_after": retry_after,
            "error": error,
            "result": {
                "source_manifest_id": manifest.get("manifest_id") if manifest else None,
                "content_sha256": content.get("content_sha256") if isinstance(content, Mapping) else None,
                "byte_length": content.get("byte_length") if isinstance(content, Mapping) else None,
            },
        }
        record["attempt_id"] = _attempt_id(record)
        record["coverage_id"] = _coverage_id(record)
        _validate_contract(record, "capital_structure_companyfacts_coverage_row.schema.json", label="Company Facts coverage row")
        _validate_coverage_identity(record)
        return record

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        """Collect at most one current Company Facts response per eligible anchored CIK.

        ``full_history`` only bypasses the seven-day freshness gate. It never expands
        beyond the current verified filing-manifest CIK set or the hard queue ceiling.
        """
        root = _data_root()
        anchor_path = root.parent / "source_manifest.parquet"
        receipt_path = root / "coverage_receipt.json"
        self._run_deadline = self._monotonic() + self.max_run_seconds
        self._run_bytes = 0
        with _companyfacts_publish_lease(root):
            signer, head_guard = self._trust_context()
            witnessed_head, witnessed_token = head_guard.read()
            source_stores = self._source_stores()
            anchor_frame = _read_ledger(anchor_path, [
                "schema", "manifest_id", "source_system", "source_id", "issuer", "filing", "document",
                "retrieval", "storage", "rights", "privacy", "parser", "spans",
            ])
            anchor_records = _records(anchor_frame)
            anchors = _complete_submission_anchor_candidates(anchor_records)
            existing_manifests, coverage_records, prior_receipt = _load_committed_bundle(
                root=root, receipt_path=receipt_path, anchor_records=anchor_records,
                signer=signer, head_witness=witnessed_head,
            )
            selection_as_of = _strict_utc(self._now_fn(), field="selection_as_of")
            retention_plan = _retention_audit_plan(existing_manifests, selection_as_of=selection_as_of)
            _verify_selected_source_objects(
                [record for record, _lane in retention_plan], source_stores=source_stores,
                deadline=self._run_deadline, monotonic=self._monotonic,
            )
            retention = _retention_verification(existing_manifests, selection_as_of=selection_as_of)
            self._require_run_time()
            queue_diagnostics: dict[str, Any] = {}
            queue, deferred_queue_count, skipped_fresh_count = select_companyfacts_queue(
                anchors, coverage_records, now=selection_as_of,
                max_ciks=self.max_ciks_per_run, force_refresh=full_history,
                cursor_sequence=int(prior_receipt["sequence"]) if prior_receipt else 0,
                diagnostics=queue_diagnostics,
            )

            def heartbeat(*, status: str, population: Mapping[str, int], published_at: datetime | pd.Timestamp,
                          selected: int, counts: Mapping[str, int], retention_verification: Mapping[str, Any],
                          anchor_verifications: Sequence[Mapping[str, Any]] = (),
                          checkpoint_blocked: bool = False) -> dict[str, pd.DataFrame]:
                stamp = _parse_stamp(published_at, field="heartbeat published_at")
                return {"sec_companyfacts_intake": pd.DataFrame({
                    "status": [status], "eligible_ciks": [len(anchors)], "selected": [selected],
                    "retrieved": [int(counts["retrieved"])], "retry": [int(counts["retry"])],
                    "deferred": [int(counts["deferred"]) + deferred_queue_count],
                    "fresh_ciks": [population["fresh_ciks"]], "stale_ciks": [population["stale_ciks"]],
                    "pending_ciks": [population["pending_ciks"]], "run_bytes": [self._run_bytes],
                    "retention_eligible_objects": [int(retention_verification["eligible_objects"])],
                    "retention_checked_objects": [len(retention_verification["verified_manifest_ids"])],
                    "retention_checked_current": [len(retention_verification["checked_current_manifest_ids"])],
                    "retention_checked_historical": [len(retention_verification["checked_historical_manifest_ids"])],
                    "retention_admission_verified": [len(retention_verification["admission_verified_manifest_ids"])],
                    "retention_freshness": [retention_verification["freshness"]],
                    "retention_all_objects_reverified": [bool(retention_verification["all_objects_reverified"])],
                    "anchor_verified": [sum(row.get("status") == "verified" for row in anchor_verifications)],
                    "anchor_failed": [sum(row.get("status") == "failed" for row in anchor_verifications)],
                    "checkpoint_blocked": [checkpoint_blocked],
                    "published_at": [_iso(stamp.to_pydatetime())],
                }, index=[pd.Timestamp(stamp.date())])}

            population = _coverage_population(anchors, coverage_records, as_of=selection_as_of)
            if prior_receipt is not None and int(prior_receipt["sequence"]) >= MAX_RECEIPT_CHAIN_LENGTH:
                message = (
                    "Company Facts receipt chain reached checkpoint/compaction boundary; "
                    "publish a compacted signed checkpoint before admitting another receipt"
                )
                print(f"::error title=companyfacts-checkpoint-blocked::{message}")
                return heartbeat(
                    status="checkpoint_blocked", population=population,
                    published_at=_parse_stamp(prior_receipt["published_at"], field="published_at"),
                    selected=0, counts={"retrieved": 0, "retry": 0, "deferred": 0},
                    retention_verification=retention, checkpoint_blocked=True,
                )

            # No selected work cannot change sealed evidence. Avoid perpetual empty
            # receipts and the O(n) startup-chain growth they cause.
            if prior_receipt is not None and not queue:
                return heartbeat(
                    status=_coverage_status(eligible_ciks=len(anchors), population=population),
                    population=population, published_at=_parse_stamp(prior_receipt["published_at"], field="published_at"),
                    selected=0, counts={"retrieved": 0, "retry": 0, "deferred": 0},
                    retention_verification=retention,
                )

            try:
                source_store = self._source_store()
                source_store_error: Exception | None = None
                source_store_id = getattr(source_store, "store_id", None)
                if isinstance(source_store_id, str):
                    source_stores.setdefault(source_store_id, source_store)
            except Exception as exc:  # noqa: BLE001
                source_store = None
                source_store_error = exc
            fresh_manifests: list[dict[str, Any]] = []
            fresh_coverage: list[dict[str, Any]] = []
            anchor_verifications: list[dict[str, Any]] = []
            counts = {"retrieved": 0, "retry": 0, "deferred": 0}
            for item in queue:
                self._require_run_budget()
                attempted = _strict_utc(self._now_fn(), field="attempted_at")
                attempted_at = _iso(attempted)
                try:
                    anchor_verifications.append(_verify_anchor_source_object(
                        item["anchor"], source_stores=source_stores,
                        deadline=self._run_deadline, monotonic=self._monotonic,
                        byte_observer=self._consume_run_bytes,
                        remaining_byte_budget=self.max_run_bytes - self._run_bytes,
                    ))
                    self._require_run_budget()
                except CompanyFactsRunBudgetExceeded:
                    raise
                except CompanyFactsAnchorVerificationError as exc:
                    error = f"{type(exc).__name__}: {exc}"[:500]
                    anchor_verifications.append(_anchor_verification_record(
                        item["anchor"], status="failed", error=error,
                    ))
                    log.warning(
                        "sec_capital_structure_companyfacts: %s deferred: %s", item["cik"], error,
                    )
                    fresh_coverage.append(self._coverage_row(
                        item=item, attempted_at=attempted_at, state="deferred", error=error,
                        retry_after=_iso(attempted + DEFER_AFTER), manifest=None,
                    ))
                    counts["deferred"] += 1
                    continue
                try:
                    if source_store is None:
                        if source_store_error is not None:
                            raise RuntimeError("content-addressed source store unavailable") from source_store_error
                        raise RuntimeError("content-addressed source store unavailable")
                    raw = self._fetch_companyfacts(item["cik"])
                    self._require_run_time()
                    receipt = source_store.put_verified(raw, media_type="application/json")
                    self._require_run_time()
                    if receipt is None:
                        raise RuntimeError("source-store write/readback verification failed")
                    retained_at = _iso(_strict_utc(self._now_fn(), field="source retained_at"))
                    manifest = self._source_manifest(
                        cik=item["cik"], anchor=item["anchor"], raw=raw, receipt=receipt, retained_at=retained_at
                    )
                    fresh_manifests.append(manifest)
                    fresh_coverage.append(self._coverage_row(
                        item=item, attempted_at=attempted_at, state="retrieved", error=None, retry_after=None, manifest=manifest
                    ))
                    counts["retrieved"] += 1
                except Exception as exc:  # noqa: BLE001
                    state, retry_deadline = _response_error_class(exc, attempted_at=attempted)
                    retry_after = _iso(retry_deadline)
                    error = f"{type(exc).__name__}: {exc}"[:500]
                    log.warning("sec_capital_structure_companyfacts: %s %s: %s", item["cik"], state, error)
                    fresh_coverage.append(self._coverage_row(
                        item=item, attempted_at=attempted_at, state=state, error=error, retry_after=retry_after, manifest=None
                    ))
                    counts[state] += 1

            combined_manifests = _append_immutable(
                existing_manifests, fresh_manifests, key="manifest_id", label="Company Facts source manifest"
            )
            combined_coverage = _append_immutable(
                coverage_records, fresh_coverage, key="coverage_id", label="Company Facts coverage row"
            )
            self._require_run_time()
            _validate_companyfacts_bundle(
                anchor_records=anchor_records, source_records=combined_manifests,
                coverage_records=combined_coverage,
            )
            retention = _retention_verification(
                existing_manifests, selection_as_of=selection_as_of, admitted_source_records=fresh_manifests,
            )
            manifest_frame = pd.DataFrame(combined_manifests, columns=_SOURCE_MANIFEST_COLUMNS)
            coverage_frame = pd.DataFrame(combined_coverage, columns=_COVERAGE_COLUMNS)
            prepared: _PreparedGeneration | None = None
            try:
                prepared = _prepare_generation(
                    source_manifests=manifest_frame, coverage=coverage_frame, root=root,
                    prior_receipt=prior_receipt, deadline=self._run_deadline, monotonic=self._monotonic,
                )
                self._require_run_time()
                published_at = _strict_utc(self._now_fn(), field="published_at")
                previous_reference = None
                if prior_receipt is not None:
                    prior_digest = str(prior_receipt["receipt_id"]).rsplit(":", 1)[-1]
                    previous_reference = _receipt_reference(
                        prior_receipt, root / "receipts" / f"{prior_digest}.json", root=root,
                    )
                sealed_receipt = _coverage_receipt(
                    selection_as_of=selection_as_of, published_at=published_at,
                    sequence=int(prior_receipt["sequence"]) + 1 if prior_receipt else 1,
                    previous_receipt=previous_reference, generation=prepared.descriptor,
                    anchor_records=anchor_records, source_records=combined_manifests,
                    coverage_records=combined_coverage, eligible_ciks=len(anchors), queue=queue,
                    max_ciks=self.max_ciks_per_run, deferred_queue_count=deferred_queue_count,
                    skipped_fresh_count=skipped_fresh_count, counts=counts,
                    queue_diagnostics=queue_diagnostics, retention_verification=retention,
                    anchor_verifications=anchor_verifications, signer=signer,
                )
                _validate_contract(sealed_receipt, "capital_structure_companyfacts_coverage_receipt.schema.json", label="Company Facts coverage receipt")
                _validate_receipt_identity(sealed_receipt)
                _validate_receipt_authentication(sealed_receipt, signer=signer)
                _validate_generation_identity(sealed_receipt)
                _validate_receipt_semantics(
                    sealed_receipt, anchor_records=anchor_records, source_records=combined_manifests,
                    coverage_records=combined_coverage, prior_source_records=existing_manifests,
                    prior_coverage_records=coverage_records,
                )
                if prior_receipt is None:
                    expected_pointer = None
                else:
                    with _open_companyfacts_parent(root, _relative_parts(root, receipt_path)) as (parent_fd, name):
                        expected_pointer = _read_regular_bytes_at(parent_fd, name, label="current pointer")
                        assert expected_pointer is not None
                _publish_generation(
                    root=root, receipt_path=receipt_path, receipt=sealed_receipt, prepared=prepared,
                    signer=signer, head_guard=head_guard, expected_witness=witnessed_head,
                    expected_witness_token=witnessed_token, expected_pointer=expected_pointer,
                )
            except Exception:
                _discard_prepared_generation(prepared)
                raise
            return heartbeat(
                status=sealed_receipt["status"], population=sealed_receipt["population"],
                published_at=published_at, selected=len(queue), counts=counts,
                retention_verification=retention, anchor_verifications=anchor_verifications,
            )


def _append_immutable(
    prior: Sequence[Mapping[str, Any]], fresh: Sequence[Mapping[str, Any]], *, key: str, label: str
) -> list[dict[str, Any]]:
    """Append exact records only; a collision with different bytes is fatal.

    Physical prior-row order is preserved and the ordered-prefix receipt makes
    any reorder, deletion, or replacement visible before the next append.
    """
    seen: dict[str, dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    for raw in [*prior, *fresh]:
        record = _native(raw)
        identity = str(record.get(key) or "")
        if not identity:
            raise CompanyFactsIntakeError(f"{label} has no {key}")
        previous = seen.get(identity)
        if previous is not None and _canonical_bytes(previous) != _canonical_bytes(record):
            raise CompanyFactsIntakeError(f"{label} immutable identity collision: {identity}")
        if previous is None:
            seen[identity] = record
            out.append(record)
    return out


def _coverage_population(
    anchors: Mapping[str, Mapping[str, Any]], coverage_records: Sequence[Mapping[str, Any]],
    *, as_of: datetime,
) -> dict[str, int]:
    stamp = _parse_stamp(as_of, field="coverage population as_of")
    latest = _latest_coverage(coverage_records)
    last_success: dict[str, dict[str, Any]] = {}
    for raw in coverage_records:
        record = _native(raw)
        if record.get("state") != "retrieved":
            continue
        cik = str(record["cik"])
        prior = last_success.get(cik)
        if prior is None or int(record["attempt_count"]) > int(prior["attempt_count"]):
            last_success[cik] = record
    population = {
        "fresh_ciks": 0, "stale_ciks": 0, "pending_ciks": 0,
        "retry_ciks": 0, "deferred_ciks": 0,
    }
    for cik in anchors:
        success = last_success.get(cik)
        if success is None:
            population["pending_ciks"] += 1
        elif _parse_stamp(success["attempted_at"], field="successful attempted_at") + REFRESH_AFTER > stamp:
            population["fresh_ciks"] += 1
        else:
            population["stale_ciks"] += 1
        current = latest.get(cik)
        if current is not None and current["state"] == "retry":
            population["retry_ciks"] += 1
        elif current is not None and current["state"] == "deferred":
            population["deferred_ciks"] += 1
    return population


def _coverage_status(*, eligible_ciks: int, population: Mapping[str, int]) -> str:
    if eligible_ciks == 0:
        return "no_eligible_anchors"
    if int(population["fresh_ciks"]) == eligible_ciks:
        return "ok"
    if int(population["fresh_ciks"]) > 0:
        return "partial"
    if int(population["stale_ciks"]) > 0:
        return "degraded"
    return "blocked"


def _validate_receipt_semantics(
    receipt: Mapping[str, Any], *, anchor_records: Sequence[Mapping[str, Any]],
    source_records: Sequence[Mapping[str, Any]], coverage_records: Sequence[Mapping[str, Any]],
    prior_source_records: Sequence[Mapping[str, Any]] = (),
    prior_coverage_records: Sequence[Mapping[str, Any]] = (),
) -> None:
    selection = _parse_stamp(receipt["selection_as_of"], field="receipt selection_as_of")
    published = _parse_stamp(receipt["published_at"], field="receipt published_at")
    if receipt["as_of"] != receipt["published_at"] or published < selection:
        raise CompanyFactsIntakeError("Company Facts receipt clocks violate publication causality")
    for source in source_records:
        if _parse_stamp(source["retrieval"]["first_seen_at"], field="source first_seen_at") > published:
            raise CompanyFactsIntakeError("receipt predates a sealed Company Facts source")
    for coverage in coverage_records:
        if _parse_stamp(coverage["attempted_at"], field="coverage attempted_at") > published:
            raise CompanyFactsIntakeError("receipt predates a sealed Company Facts attempt")
    if _ledger_receipt(anchor_records) != receipt["anchor_manifest_ledger"]:
        raise CompanyFactsIntakeError("receipt anchor ordered-prefix commitment mismatch")
    if _ledger_receipt(source_records) != receipt["companyfacts_manifest_ledger"]:
        raise CompanyFactsIntakeError("receipt source ordered-prefix commitment mismatch")
    if _ledger_receipt(coverage_records) != receipt["coverage_ledger"]:
        raise CompanyFactsIntakeError("receipt coverage ordered-prefix commitment mismatch")
    queue = receipt["queue"]
    counts = receipt["counts"]
    selected = int(queue["selected_ciks"])
    if selected != len(queue["priority_order"]):
        raise CompanyFactsIntakeError("receipt selected count/priority order mismatch")
    anchor_verifications = queue.get("anchor_verifications")
    if not isinstance(anchor_verifications, list) or len(anchor_verifications) != selected:
        raise CompanyFactsIntakeError("receipt selected count/anchor verification mismatch")
    if selected > int(queue["max_ciks"]) or int(queue["eligible_ciks"]) < selected:
        raise CompanyFactsIntakeError("receipt queue bounds are inconsistent")
    if selected != int(counts["retrieved"]) + int(counts["retry"]) + int(counts["deferred"]):
        raise CompanyFactsIntakeError("receipt selected count/outcome count mismatch")
    for reason in ("retry_due", "new_anchor", "refresh_due"):
        due = int(queue["due_by_reason"][reason])
        selected_for_reason = int(queue["selected_by_reason"][reason])
        if selected_for_reason > due:
            raise CompanyFactsIntakeError("receipt selected lane count exceeds due lane count")
    if sum(int(value) for value in queue["selected_by_reason"].values()) != selected:
        raise CompanyFactsIntakeError("receipt selected lane counts do not sum to selected_ciks")
    anchors = _complete_submission_anchor_candidates(anchor_records)
    eligible = len(anchors)
    if eligible != int(queue["eligible_ciks"]):
        raise CompanyFactsIntakeError("receipt eligible count does not match verified anchors")
    population = _coverage_population(anchors, coverage_records, as_of=published.to_pydatetime())
    if dict(receipt["population"]) != population:
        raise CompanyFactsIntakeError("receipt population does not match committed coverage")
    if population["fresh_ciks"] + population["stale_ciks"] + population["pending_ciks"] != eligible:
        raise CompanyFactsIntakeError("receipt population partition does not sum to eligible CIKs")
    expected_status = _coverage_status(eligible_ciks=eligible, population=population)
    if receipt["status"] != expected_status:
        raise CompanyFactsIntakeError("receipt status does not match committed population")
    sequence = int(receipt["sequence"])
    previous = receipt.get("previous_receipt")
    if (sequence == 1) != (previous is None):
        raise CompanyFactsIntakeError("receipt genesis/predecessor invariant mismatch")
    if len(prior_source_records) > len(source_records) or len(prior_coverage_records) > len(coverage_records):
        raise CompanyFactsIntakeError("receipt predecessor generation exceeds current generation")
    if (
        [_canonical_bytes(_native(row)) for row in source_records[:len(prior_source_records)]]
        != [_canonical_bytes(_native(row)) for row in prior_source_records]
        or [_canonical_bytes(_native(row)) for row in coverage_records[:len(prior_coverage_records)]]
        != [_canonical_bytes(_native(row)) for row in prior_coverage_records]
    ):
        raise CompanyFactsIntakeError("receipt generation is not an exact predecessor prefix")
    source_suffix = [_native(row) for row in source_records[len(prior_source_records):]]
    coverage_suffix = [_native(row) for row in coverage_records[len(prior_coverage_records):]]
    expected_queue_diagnostics: dict[str, Any] = {}
    expected_queue, expected_deferred, expected_skipped = select_companyfacts_queue(
        anchors,
        prior_coverage_records,
        now=selection.to_pydatetime(),
        max_ciks=int(queue["max_ciks"]),
        force_refresh=bool(queue["force_refresh"]),
        cursor_sequence=int(queue["cursor_sequence"]),
        diagnostics=expected_queue_diagnostics,
    )
    if (
        [item["cik"] for item in expected_queue] != list(queue["priority_order"])
        or int(queue["deferred_ciks"]) != expected_deferred
        or int(counts["skipped_fresh"]) != expected_skipped
        or dict(queue["due_by_reason"]) != expected_queue_diagnostics["due_by_reason"]
        or dict(queue["selected_by_reason"]) != expected_queue_diagnostics["selected_by_reason"]
    ):
        raise CompanyFactsIntakeError("receipt queue telemetry is detached from its predecessor state")
    if len(coverage_suffix) != selected:
        raise CompanyFactsIntakeError("receipt selected count does not match coverage suffix")
    observed_counts = {state: sum(row.get("state") == state for row in coverage_suffix) for state in ("retrieved", "retry", "deferred")}
    if any(int(counts[state]) != observed_counts[state] for state in observed_counts):
        raise CompanyFactsIntakeError("receipt outcome counts do not match coverage suffix")
    for item, row, verification in zip(
        expected_queue, coverage_suffix, anchor_verifications, strict=True,
    ):
        if (
            row.get("cik") != item["cik"]
            or row.get("anchor_manifest_id") != item["anchor"]["manifest_id"]
            or int(row.get("attempt_count") or 0) != int(item["attempt_count"])
            or row.get("queue_reason") != item["queue_reason"]
        ):
            raise CompanyFactsIntakeError("receipt coverage suffix is detached from selected queue")
        if not isinstance(verification, Mapping):
            raise CompanyFactsIntakeError("receipt anchor verification is malformed")
        expected_binding = _anchor_storage_binding(item["anchor"])
        if any(verification.get(key) != value for key, value in expected_binding.items()):
            raise CompanyFactsIntakeError("receipt anchor verification is detached from selected anchor")
        verification_status = verification.get("status")
        verification_error = verification.get("error")
        if verification_status == "verified":
            if verification_error is not None:
                raise CompanyFactsIntakeError("verified anchor carries a failure error")
        elif verification_status == "failed":
            if (
                not isinstance(verification_error, str)
                or not verification_error
                or row.get("state") != "deferred"
                or row.get("error") != verification_error
            ):
                raise CompanyFactsIntakeError("failed anchor verification is detached from deferred coverage")
        else:
            raise CompanyFactsIntakeError("receipt anchor verification status is invalid")
    source_ids = {str(row.get("manifest_id")) for row in source_suffix}
    retrieved_source_ids = {
        str(row["result"]["source_manifest_id"])
        for row in coverage_suffix if row.get("state") == "retrieved"
    }
    if source_ids != retrieved_source_ids or len(source_suffix) != observed_counts["retrieved"]:
        raise CompanyFactsIntakeError("receipt source suffix is detached from retrieved coverage")
    expected_retention = _retention_verification(
        prior_source_records, selection_as_of=selection.to_pydatetime(),
        admitted_source_records=source_suffix,
    )
    if dict(receipt.get("retention_verification") or {}) != expected_retention:
        raise CompanyFactsIntakeError("receipt retention verification coverage is detached from its source history")


def _coverage_receipt(
    *, selection_as_of: datetime, published_at: datetime, sequence: int,
    previous_receipt: Mapping[str, Any] | None, generation: Mapping[str, Any],
    anchor_records: Sequence[Mapping[str, Any]], source_records: Sequence[Mapping[str, Any]],
    coverage_records: Sequence[Mapping[str, Any]], eligible_ciks: int, queue: Sequence[Mapping[str, Any]], max_ciks: int,
    deferred_queue_count: int, skipped_fresh_count: int, counts: Mapping[str, int],
    queue_diagnostics: Mapping[str, Any], retention_verification: Mapping[str, Any],
    anchor_verifications: Sequence[Mapping[str, Any]], signer: CompanyFactsSigner,
) -> dict[str, Any]:
    published_at = _strict_utc(published_at, field="published_at")
    selection_as_of = _strict_utc(selection_as_of, field="selection_as_of")
    anchors = _complete_submission_anchor_candidates(anchor_records)
    population = _coverage_population(anchors, coverage_records, as_of=published_at)
    record: dict[str, Any] = {
        "schema": COVERAGE_RECEIPT_SCHEMA,
        "selection_as_of": _iso(selection_as_of),
        "published_at": _iso(published_at),
        "as_of": _iso(published_at),
        "sequence": sequence,
        "previous_receipt": dict(previous_receipt) if previous_receipt is not None else None,
        "policy_version": POLICY_VERSION,
        "status": _coverage_status(eligible_ciks=eligible_ciks, population=population),
        "generation": dict(generation),
        "anchor_manifest_ledger": _ledger_receipt(anchor_records),
        "companyfacts_manifest_ledger": _ledger_receipt(source_records),
        "coverage_ledger": _ledger_receipt(coverage_records),
        "retention_verification": dict(retention_verification),
        "queue": {
            "max_ciks": max_ciks,
            "force_refresh": bool(queue_diagnostics["force_refresh"]),
            "cursor_sequence": int(queue_diagnostics["cursor_sequence"]),
            "eligible_ciks": eligible_ciks,
            "selected_ciks": len(queue),
            "deferred_ciks": deferred_queue_count,
            "priority_order": [str(item["cik"]) for item in queue],
            "due_by_reason": dict(queue_diagnostics["due_by_reason"]),
            "selected_by_reason": dict(queue_diagnostics["selected_by_reason"]),
            "anchor_verifications": [dict(row) for row in anchor_verifications],
        },
        "counts": {
            "retrieved": int(counts["retrieved"]), "retry": int(counts["retry"]),
            "deferred": int(counts["deferred"]), "skipped_fresh": skipped_fresh_count,
        },
        "population": population,
        "nonclaims": _NONCLAIMS,
        "authority": _authority(),
        "auth": {"scheme": RECEIPT_AUTH_SCHEME, "key_id": signer.key_id, "signature": ""},
    }
    return _sign_receipt(record, signer=signer)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    SecCapitalStructureCompanyFactsAdapter().fetch()
