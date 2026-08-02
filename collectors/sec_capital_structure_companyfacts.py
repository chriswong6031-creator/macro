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
from dataclasses import dataclass, field
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
    ManifestIdentityError,
    validate_manifest_content_binding,
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
MAX_POINTER_BYTES = 16 * 1024
MAX_HEAD_WITNESS_BYTES = 16 * 1024
MAX_RECEIPT_BYTES = 4 * 1024 * 1024
MAX_ANCHOR_LEDGER_BYTES = 128 * 1024 * 1024
MAX_GENERATION_FILE_BYTES = 128 * 1024 * 1024
# Retention verification is deliberately bounded: source admission remains an
# exact put/readback, while pre-existing immutable objects receive a rotating
# audit instead of an unbounded all-history startup scan.
MAX_RETENTION_VERIFY_OBJECTS = 24
RETENTION_VERIFY_POLICY = "bounded-retention-verification/v1"
RUN_BYTE_ACCOUNTING = (
    "anchor-read+retention-read+sec-response+source-write-reservation+"
    "source-readback-reservation/v1"
)
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
            head = self._client.head_object(Bucket=self._bucket, Key=self._key)
        except Exception as exc:  # noqa: BLE001
            if _is_not_found_error(exc):
                return None, None
            raise CompanyFactsIntakeError("Company Facts external head witness is unreadable") from exc
        if not isinstance(head, Mapping):
            raise CompanyFactsIntakeError("Company Facts external head witness HEAD is malformed")
        expected_length = head.get("ContentLength")
        if (
            isinstance(expected_length, bool)
            or not isinstance(expected_length, int)
            or expected_length < 1
            or expected_length > MAX_HEAD_WITNESS_BYTES
        ):
            raise CompanyFactsIntakeError(
                "Company Facts external head witness HEAD length exceeds its byte cap"
            )
        etag = head.get("ETag")
        if not isinstance(etag, str) or not etag.strip():
            raise CompanyFactsIntakeError("Company Facts external head witness HEAD has no CAS token")
        try:
            response = self._client.get_object(
                Bucket=self._bucket,
                Key=self._key,
                Range=f"bytes=0-{expected_length}",
                IfMatch=etag,
            )
        except Exception as exc:  # noqa: BLE001
            # Once HEAD established an object, every GET failure (including a
            # later 404 or 412) is an unreadable/rebound witness, never absence.
            raise CompanyFactsIntakeError("Company Facts external head witness is unreadable") from exc
        if not isinstance(response, Mapping):
            raise CompanyFactsIntakeError("Company Facts external head witness GET is malformed")
        body_stream = response.get("Body")
        if body_stream is None:
            raise CompanyFactsIntakeError("Company Facts external head witness body is unreadable")
        try:
            if (
                not callable(getattr(body_stream, "read", None))
                or not callable(getattr(body_stream, "close", None))
            ):
                raise CompanyFactsIntakeError(
                    "Company Facts external head witness body is unreadable"
                )
            response_length = response.get("ContentLength")
            if (
                isinstance(response_length, bool)
                or not isinstance(response_length, int)
                or response_length != expected_length
            ):
                raise CompanyFactsIntakeError(
                    "Company Facts external head witness GET/HEAD length mismatch"
                )
            if response.get("ETag") != etag:
                raise CompanyFactsIntakeError(
                    "Company Facts external head witness GET/HEAD CAS token mismatch"
                )
            chunks: list[bytes] = []
            observed = 0
            boundary = expected_length + 1
            while observed < boundary:
                requested = min(64 * 1024, boundary - observed)
                chunk = body_stream.read(requested)
                if not isinstance(chunk, bytes):
                    raise CompanyFactsIntakeError(
                        "Company Facts external head witness body returned non-bytes"
                    )
                if not chunk:
                    break
                if len(chunk) > requested:
                    raise CompanyFactsIntakeError(
                        "Company Facts external head witness body violated its read boundary"
                    )
                observed += len(chunk)
                chunks.append(chunk)
            body = b"".join(chunks)
            if len(body) != expected_length:
                raise CompanyFactsIntakeError(
                    "Company Facts external head witness body length mismatch"
                )
            witness = _native(json.loads(body))
            if body != _canonical_bytes(witness) + b"\n":
                raise CompanyFactsIntakeError("Company Facts external head witness bytes are not canonical")
            _validate_head_witness(witness, signer=self._signer)
            # Preserve the service-supplied ETag syntax. The S3/R2 conditional
            # request header is an entity-tag and SDK callers conventionally pass
            # the quoted value returned by HEAD straight back as IfMatch.
            return dict(witness), etag
        except CompanyFactsIntakeError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise CompanyFactsIntakeError("Company Facts external head witness is malformed") from exc
        finally:
            close = getattr(body_stream, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as exc:  # noqa: BLE001 - cleanup is part of strict read
                    raise CompanyFactsIntakeError(
                        "Company Facts external head witness body close failed"
                    ) from exc

    def advance(
        self, *, expected: Mapping[str, Any] | None, expected_token: str | None,
        candidate: Mapping[str, Any],
    ) -> None:
        observed, token = self.read()
        normalized_expected = dict(expected) if expected is not None else None
        if observed != normalized_expected or token != expected_token:
            raise CompanyFactsIntakeError("Company Facts external head witness compare-and-swap conflict")
        _validate_head_transition(previous=observed, candidate=candidate, signer=self._signer)
        candidate_body = _canonical_bytes(dict(candidate)) + b"\n"
        if len(candidate_body) > MAX_HEAD_WITNESS_BYTES:
            raise CompanyFactsIntakeError("Company Facts external head witness exceeds byte cap")
        arguments: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": self._key,
            "Body": candidate_body,
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


def _read_ledger(
    path: Path, columns: Sequence[str], *, max_bytes: int,
    parent_fd: int | None = None,
) -> pd.DataFrame:
    try:
        if parent_fd is not None:
            body = _read_regular_bytes_at(
                parent_fd, path.name, label=f"ledger {path.name}",
                max_bytes=max_bytes, missing_ok=True,
            )
        else:
            with _open_absolute_directory(path.parent) as opened_parent_fd:
                body = _read_regular_bytes_at(
                    opened_parent_fd, path.name, label=f"ledger {path.name}",
                    max_bytes=max_bytes, missing_ok=True,
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


@dataclass(frozen=True)
class _CompanyFactsLane:
    root: Path
    parent_fd: int
    root_fd: int
    parent_device: int
    parent_inode: int
    root_device: int
    root_inode: int
    generations_fd: int
    generations_device: int
    generations_inode: int
    receipts_fd: int
    receipts_device: int
    receipts_inode: int


def _lane_child_binding(lane: _CompanyFactsLane, name: str) -> tuple[int, int, int]:
    if name == "generations":
        return lane.generations_fd, lane.generations_device, lane.generations_inode
    if name == "receipts":
        return lane.receipts_fd, lane.receipts_device, lane.receipts_inode
    raise CompanyFactsIntakeError(f"Company Facts lane has no held child namespace: {name}")


def _assert_lane_child_identity(lane: _CompanyFactsLane, name: str) -> None:
    descriptor, device, inode = _lane_child_binding(lane, name)
    opened = os.fstat(descriptor)
    if not stat.S_ISDIR(opened.st_mode) or (opened.st_dev, opened.st_ino) != (device, inode):
        raise CompanyFactsIntakeError(f"Company Facts held {name} descriptor identity changed")
    try:
        bound = os.stat(name, dir_fd=lane.root_fd, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise CompanyFactsIntakeError(
            f"Company Facts held {name} namespace was renamed during transaction"
        ) from exc
    if stat.S_ISLNK(bound.st_mode) or (bound.st_dev, bound.st_ino) != (device, inode):
        raise CompanyFactsIntakeError(
            f"Company Facts held {name} namespace was rebound during transaction"
        )


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
    lane: _CompanyFactsLane | None = None,
) -> Iterator[int]:
    """Open the absolute lane root and all descendants without following links.

    The root itself is never created with ``Path.mkdir(parents=True)``. Every
    ancestor starts at the trusted filesystem root and crosses an lstat/openat
    identity check, so a missing lane beneath an ancestor symlink cannot escape.
    """
    descriptors: list[int] = []
    if lane is not None:
        if root != lane.root:
            raise CompanyFactsIntakeError("Company Facts lane descriptor is bound to a different root")
        opened = os.fstat(lane.root_fd)
        if (opened.st_dev, opened.st_ino) != (lane.root_device, lane.root_inode):
            raise CompanyFactsIntakeError("Company Facts held lane-root descriptor identity changed")
        try:
            start = 0
            if parts and parts[0] in {"generations", "receipts"}:
                namespace = parts[0]
                _assert_lane_child_identity(lane, namespace)
                namespace_fd, _, _ = _lane_child_binding(lane, namespace)
                current = os.dup(namespace_fd)
                start = 1
            else:
                current = os.dup(lane.root_fd)
            descriptors.append(current)
            rendered: list[str] = []
            for part in parts[start:]:
                rendered.append(part)
                current = _open_verified_directory_component(
                    current, part, create=create, label="/".join(rendered),
                )
                descriptors.append(current)
            yield current
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)
        return
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
    lane: _CompanyFactsLane | None = None,
) -> Iterator[tuple[int, str]]:
    if not parts:
        raise CompanyFactsIntakeError("Company Facts file path is required")
    if any(part in {"", ".", ".."} or "/" in part or "\\" in part for part in parts):
        raise CompanyFactsIntakeError("Company Facts path traversal is forbidden")
    with _open_companyfacts_directory(root, parts[:-1], create=create, lane=lane) as parent_fd:
        yield parent_fd, parts[-1]


def _read_regular_bytes_at(
    parent_fd: int, name: str, *, label: str, max_bytes: int,
    expected_byte_length: int | None = None, missing_ok: bool = False,
) -> bytes | None:
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 0:
        raise CompanyFactsIntakeError(f"Company Facts {label} has an invalid byte cap")
    if (
        expected_byte_length is not None
        and (
            isinstance(expected_byte_length, bool)
            or not isinstance(expected_byte_length, int)
            or expected_byte_length < 0
            or expected_byte_length > max_bytes
        )
    ):
        raise CompanyFactsIntakeError(f"Company Facts {label} has an invalid exact length")
    try:
        descriptor = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise CompanyFactsIntakeError(f"Company Facts {label} is missing") from None
    except OSError as exc:
        raise CompanyFactsIntakeError(f"Company Facts {label} cannot be opened without following links") from exc
    try:
        body = _read_regular_descriptor_bytes(
            descriptor, label=label, max_bytes=max_bytes,
            expected_byte_length=expected_byte_length,
        )
        opened = os.fstat(descriptor)
        try:
            bound = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise CompanyFactsIntakeError(
                f"Company Facts {label} was renamed during secure read"
            ) from exc
        if stat.S_ISLNK(bound.st_mode) or (bound.st_dev, bound.st_ino) != (
            opened.st_dev, opened.st_ino,
        ):
            raise CompanyFactsIntakeError(f"Company Facts {label} was rebound during secure read")
        return body
    finally:
        os.close(descriptor)


def _read_regular_descriptor_bytes(
    descriptor: int, *, label: str, max_bytes: int,
    expected_byte_length: int | None,
) -> bytes:
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 0:
        raise CompanyFactsIntakeError(f"Company Facts {label} has an invalid byte cap")
    if (
        expected_byte_length is not None
        and (
            isinstance(expected_byte_length, bool)
            or not isinstance(expected_byte_length, int)
            or expected_byte_length < 0
            or expected_byte_length > max_bytes
        )
    ):
        raise CompanyFactsIntakeError(f"Company Facts {label} has an invalid exact length")
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        raise CompanyFactsIntakeError(f"Company Facts {label} must be a regular file")
    if before.st_size > max_bytes:
        raise CompanyFactsIntakeError(f"Company Facts {label} exceeds byte cap")
    if expected_byte_length is not None and before.st_size != expected_byte_length:
        raise CompanyFactsIntakeError(f"Company Facts {label} exact-byte length mismatch")
    expected = before.st_size if expected_byte_length is None else expected_byte_length
    # Held descriptors are reread at every publication boundary.
    os.lseek(descriptor, 0, os.SEEK_SET)
    boundary = min(expected, max_bytes) + 1
    chunks: list[bytes] = []
    observed = 0
    while observed < boundary:
        chunk = os.read(descriptor, min(1024 * 1024, boundary - observed))
        if not chunk:
            break
        chunks.append(chunk)
        observed += len(chunk)
    body = b"".join(chunks)
    if len(body) != expected:
        raise CompanyFactsIntakeError(f"Company Facts {label} changed during secure read")
    after = os.fstat(descriptor)
    if _regular_metadata_fingerprint(before) != _regular_metadata_fingerprint(after):
        raise CompanyFactsIntakeError(f"Company Facts {label} metadata changed during secure read")
    return body


def _regular_metadata_fingerprint(metadata: os.stat_result) -> tuple[Any, ...]:
    return (
        metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_size,
        getattr(metadata, "st_mtime_ns", None), getattr(metadata, "st_ctime_ns", None),
    )


@dataclass
class _HeldRegularFile:
    """A regular file and its parent namespace retained across publication."""

    parent_fd: int
    parent_device: int
    parent_inode: int
    name: str
    descriptor: int
    fingerprint: tuple[Any, ...]


def _hold_regular_file_at(parent_fd: int, name: str, *, label: str) -> _HeldRegularFile:
    held_parent: int | None = None
    descriptor: int | None = None
    try:
        held_parent = os.dup(parent_fd)
        parent_metadata = os.fstat(held_parent)
        if not stat.S_ISDIR(parent_metadata.st_mode):
            raise CompanyFactsIntakeError(f"Company Facts {label} parent must be a directory")
        descriptor = os.open(
            name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=held_parent,
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise CompanyFactsIntakeError(f"Company Facts {label} must be a regular file")
        bound = os.stat(name, dir_fd=held_parent, follow_symlinks=False)
        if stat.S_ISLNK(bound.st_mode) or (bound.st_dev, bound.st_ino) != (
            metadata.st_dev, metadata.st_ino,
        ):
            raise CompanyFactsIntakeError(f"Company Facts {label} was rebound while retained")
        held = _HeldRegularFile(
            parent_fd=held_parent,
            parent_device=parent_metadata.st_dev,
            parent_inode=parent_metadata.st_ino,
            name=name,
            descriptor=descriptor,
            fingerprint=_regular_metadata_fingerprint(metadata),
        )
        held_parent = None
        descriptor = None
        return held
    except CompanyFactsIntakeError:
        raise
    except OSError as exc:
        raise CompanyFactsIntakeError(
            f"Company Facts {label} cannot be retained without following links"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if held_parent is not None:
            os.close(held_parent)


def _release_held_regular_file(held: _HeldRegularFile) -> None:
    os.close(held.descriptor)
    os.close(held.parent_fd)


def _assert_held_regular_file_binding(
    held: _HeldRegularFile, *, current_parent_fd: int, expected_body: bytes,
    max_bytes: int, label: str,
) -> dict[str, Any]:
    parent_metadata = os.fstat(held.parent_fd)
    current_parent = os.fstat(current_parent_fd)
    if (
        not stat.S_ISDIR(parent_metadata.st_mode)
        or (parent_metadata.st_dev, parent_metadata.st_ino) != (
            held.parent_device, held.parent_inode,
        )
        or (current_parent.st_dev, current_parent.st_ino) != (
            held.parent_device, held.parent_inode,
        )
    ):
        raise CompanyFactsIntakeError(f"Company Facts {label} parent namespace was rebound")
    metadata = os.fstat(held.descriptor)
    if _regular_metadata_fingerprint(metadata) != held.fingerprint:
        raise CompanyFactsIntakeError(f"Company Facts {label} descriptor metadata changed")
    try:
        bound = os.stat(held.name, dir_fd=held.parent_fd, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise CompanyFactsIntakeError(f"Company Facts {label} was renamed") from exc
    if stat.S_ISLNK(bound.st_mode) or (bound.st_dev, bound.st_ino) != (
        metadata.st_dev, metadata.st_ino,
    ):
        raise CompanyFactsIntakeError(f"Company Facts {label} was rebound")
    body = _read_regular_descriptor_bytes(
        held.descriptor, label=label, max_bytes=max_bytes,
        expected_byte_length=len(expected_body),
    )
    expected_receipt = _bytes_receipt(expected_body)
    observed_receipt = _bytes_receipt(body)
    if observed_receipt != expected_receipt:
        raise CompanyFactsIntakeError(f"Company Facts {label} exact-byte receipt mismatch")
    if _regular_metadata_fingerprint(os.fstat(held.descriptor)) != held.fingerprint:
        raise CompanyFactsIntakeError(f"Company Facts {label} descriptor metadata changed")
    rebound = os.stat(held.name, dir_fd=held.parent_fd, follow_symlinks=False)
    if stat.S_ISLNK(rebound.st_mode) or (rebound.st_dev, rebound.st_ino) != (
        metadata.st_dev, metadata.st_ino,
    ):
        raise CompanyFactsIntakeError(f"Company Facts {label} was rebound")
    return observed_receipt


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


def _fsync_held_directory(descriptor: int, path: Path) -> None:
    """Durably flush an already-bound directory; ``path`` is diagnostics only."""
    del path
    os.fsync(descriptor)


def _assert_lane_path_identity(lane: _CompanyFactsLane) -> None:
    """Prove the held lane is still the configured absolute namespace target."""
    parent = os.fstat(lane.parent_fd)
    root = os.fstat(lane.root_fd)
    if (
        not stat.S_ISDIR(parent.st_mode)
        or (parent.st_dev, parent.st_ino) != (lane.parent_device, lane.parent_inode)
        or not stat.S_ISDIR(root.st_mode)
        or (root.st_dev, root.st_ino) != (lane.root_device, lane.root_inode)
    ):
        raise CompanyFactsIntakeError("Company Facts held lane descriptor identity changed")
    try:
        bound = os.stat(lane.root.name, dir_fd=lane.parent_fd, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise CompanyFactsIntakeError("Company Facts lane root was renamed during transaction") from exc
    if stat.S_ISLNK(bound.st_mode) or (bound.st_dev, bound.st_ino) != (
        lane.root_device, lane.root_inode,
    ):
        raise CompanyFactsIntakeError("Company Facts lane root was rebound during transaction")

    # Detect a rename/replacement of the held parent itself. This traversal is
    # read-only continuity proof; all transaction reads and writes still descend
    # exclusively from the held root descriptor above.
    with _open_absolute_directory(lane.root.parent) as current_parent_fd:
        current_parent = os.fstat(current_parent_fd)
        if (current_parent.st_dev, current_parent.st_ino) != (
            lane.parent_device, lane.parent_inode,
        ):
            raise CompanyFactsIntakeError("Company Facts lane parent was rebound during transaction")
        current_root = os.stat(lane.root.name, dir_fd=current_parent_fd, follow_symlinks=False)
        if stat.S_ISLNK(current_root.st_mode) or (current_root.st_dev, current_root.st_ino) != (
            lane.root_device, lane.root_inode,
        ):
            raise CompanyFactsIntakeError("Company Facts lane root was rebound during transaction")
    _assert_lane_child_identity(lane, "generations")
    _assert_lane_child_identity(lane, "receipts")


@contextmanager
def _companyfacts_publish_lease(root: Path) -> Iterator[_CompanyFactsLane]:
    """Mandatory cross-process lease spanning load, network work, and publish.

    The external R2 witness remains the cross-host CAS authority; this lock
    prevents two local processes from doing duplicate network work or forking
    the on-disk receipt chain before that CAS point.
    """
    if not root.is_absolute() or root.name in {"", ".", ".."}:
        raise CompanyFactsIntakeError("Company Facts lane root must be an absolute child path")
    with _open_absolute_directory(root.parent, create=True) as parent_fd:
        root_fd = _open_verified_directory_component(
            parent_fd, root.name, create=True, label=str(root),
        )
        lock_fd: int | None = None
        generations_fd: int | None = None
        receipts_fd: int | None = None
        try:
            try:
                lock_fd = os.open(
                    ".companyfacts_publish.lock",
                    os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=root_fd,
                )
            except OSError as exc:
                raise CompanyFactsIntakeError(
                    "Company Facts publish lease cannot follow a symlink"
                ) from exc
            if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
                raise CompanyFactsIntakeError("Company Facts publish lease must be a regular file")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                generations_fd = _open_verified_directory_component(
                    root_fd, "generations", create=True, label=f"{root}/generations",
                )
                receipts_fd = _open_verified_directory_component(
                    root_fd, "receipts", create=True, label=f"{root}/receipts",
                )
                parent_stat = os.fstat(parent_fd)
                root_stat = os.fstat(root_fd)
                generations_stat = os.fstat(generations_fd)
                receipts_stat = os.fstat(receipts_fd)
                yield _CompanyFactsLane(
                    root=root, parent_fd=parent_fd, root_fd=root_fd,
                    parent_device=parent_stat.st_dev, parent_inode=parent_stat.st_ino,
                    root_device=root_stat.st_dev, root_inode=root_stat.st_ino,
                    generations_fd=generations_fd,
                    generations_device=generations_stat.st_dev,
                    generations_inode=generations_stat.st_ino,
                    receipts_fd=receipts_fd,
                    receipts_device=receipts_stat.st_dev,
                    receipts_inode=receipts_stat.st_ino,
                )
            finally:
                if receipts_fd is not None:
                    os.close(receipts_fd)
                if generations_fd is not None:
                    os.close(generations_fd)
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            if lock_fd is not None:
                os.close(lock_fd)
            os.close(root_fd)


def _atomic_write_bytes(
    path: Path, content: bytes, *, expected_previous: bytes | None | object = ...,
    root: Path | None = None, lane: _CompanyFactsLane | None = None,
) -> None:
    """Atomically replace a pointer under an exact-predecessor publication lease.

    A directory-fsync failure is intentionally *not* softened: visibility after
    ``os.replace`` is not a durability acknowledgement. The external head witness
    records the recovery target, while this call reports an indeterminate publish.
    """
    if len(content) > MAX_POINTER_BYTES:
        raise CompanyFactsIntakeError("Company Facts current pointer exceeds byte cap")
    safe_root = root or path.parent
    if lane is not None:
        _assert_lane_path_identity(lane)
    parts = _relative_parts(safe_root, path) if root is not None else _safe_relative_parts(path.name)
    temporary = f".{parts[-1]}.{os.getpid()}.{time.time_ns()}.tmp"
    with _open_companyfacts_parent(safe_root, parts, create=True, lane=lane) as (parent_fd, name):
        previous = _read_regular_bytes_at(
            parent_fd, name, label="current pointer", max_bytes=MAX_POINTER_BYTES,
            expected_byte_length=(len(expected_previous) if isinstance(expected_previous, bytes) else None),
            missing_ok=True,
        )
        if expected_previous is not ... and previous != expected_previous:
            raise CompanyFactsIntakeError(f"Company Facts pointer exact-predecessor CAS conflict: {path}")
        try:
            _write_new_regular_bytes_at(parent_fd, temporary, content, label="staged pointer")
            if _read_regular_bytes_at(
                parent_fd, temporary, label="staged pointer", max_bytes=MAX_POINTER_BYTES,
                expected_byte_length=len(content),
            ) != content:
                raise CompanyFactsIntakeError(f"staged pointer read-back mismatch: {path}")
            try:
                # Re-check via the same parent descriptor immediately before commit.
                if expected_previous is not ...:
                    observed = _read_regular_bytes_at(
                        parent_fd, name, label="current pointer", max_bytes=MAX_POINTER_BYTES,
                        expected_byte_length=(
                            len(expected_previous) if isinstance(expected_previous, bytes) else None
                        ),
                        missing_ok=True,
                    )
                    if observed != expected_previous:
                        raise CompanyFactsIntakeError(
                            f"Company Facts pointer exact-predecessor CAS conflict: {path}"
                        )
                if lane is not None:
                    _assert_lane_path_identity(lane)
                os.replace(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            except Exception:
                actual = _read_regular_bytes_at(
                    parent_fd, name, label="current pointer", max_bytes=MAX_POINTER_BYTES,
                    expected_byte_length=(len(previous) if isinstance(previous, bytes) else None),
                    missing_ok=True,
                )
                if actual != previous:
                    raise CompanyFactsIntakeError(f"Company Facts pointer state uncertain: {path}")
                raise
            try:
                _fsync_held_directory(parent_fd, path.parent)
                if lane is not None:
                    _assert_lane_path_identity(lane)
            except Exception as exc:
                raise CompanyFactsPublishIndeterminate(
                    f"Company Facts pointer durability is indeterminate after replace: {path}"
                ) from exc
        finally:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass


def _write_immutable_bytes(
    path: Path, content: bytes, *, root: Path | None = None,
    lane: _CompanyFactsLane | None = None,
) -> None:
    """Create one immutable object without ever replacing a divergent target."""
    if len(content) > MAX_RECEIPT_BYTES:
        raise CompanyFactsIntakeError("Company Facts immutable receipt exceeds byte cap")
    safe_root = root or path.parent
    if lane is not None:
        _assert_lane_path_identity(lane)
    parts = _relative_parts(safe_root, path) if root is not None else _safe_relative_parts(path.name)
    temporary = f".{parts[-1]}.{os.getpid()}.{time.time_ns()}.tmp"
    with _open_companyfacts_parent(safe_root, parts, create=True, lane=lane) as (parent_fd, name):
        existing = _read_regular_bytes_at(
            parent_fd, name, label="immutable object", max_bytes=MAX_RECEIPT_BYTES,
            expected_byte_length=len(content), missing_ok=True,
        )
        if existing is not None:
            if existing != content:
                raise CompanyFactsIntakeError(f"immutable Company Facts object collision: {path}")
            return
        try:
            _write_new_regular_bytes_at(parent_fd, temporary, content, label="immutable staged object")
            if _read_regular_bytes_at(
                parent_fd, temporary, label="immutable staged object",
                max_bytes=MAX_RECEIPT_BYTES, expected_byte_length=len(content),
            ) != content:
                raise CompanyFactsIntakeError(f"immutable Company Facts object read-back mismatch: {path}")
            try:
                if lane is not None:
                    _assert_lane_path_identity(lane)
                os.link(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd, follow_symlinks=False)
            except FileExistsError:
                existing = _read_regular_bytes_at(
                    parent_fd, name, label="immutable object", max_bytes=MAX_RECEIPT_BYTES,
                    expected_byte_length=len(content),
                )
                if existing != content:
                    raise CompanyFactsIntakeError(f"immutable Company Facts object collision: {path}")
            _fsync_held_directory(parent_fd, path.parent)
            if lane is not None:
                _assert_lane_path_identity(lane)
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


def _file_receipt(
    path: Path, *, max_bytes: int, expected_byte_length: int | None = None,
    root: Path | None = None, lane: _CompanyFactsLane | None = None,
) -> dict[str, Any]:
    if root is None:
        with _open_absolute_directory(path.parent) as parent_fd:
            body = _read_regular_bytes_at(
                parent_fd, path.name, label="file receipt", max_bytes=max_bytes,
                expected_byte_length=expected_byte_length,
            )
            assert body is not None
    else:
        parts = _relative_parts(root, path)
        with _open_companyfacts_parent(root, parts, lane=lane) as (parent_fd, name):
            body = _read_regular_bytes_at(
                parent_fd, name, label="file receipt", max_bytes=max_bytes,
                expected_byte_length=expected_byte_length,
            )
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


@dataclass
class _PreparedGeneration:
    descriptor: dict[str, Any]
    stage_path: Path | None
    stage_fd: int | None = None
    stage_device: int | None = None
    stage_inode: int | None = None
    installed_name: str | None = None
    generation_files: dict[str, tuple[int, tuple[Any, ...]]] = field(default_factory=dict)


def _assert_stage_inode_binding(
    parent_fd: int, name: str, stage_fd: int | None,
    stage_device: int | None, stage_inode: int | None, *, label: str,
) -> None:
    if stage_fd is None or stage_device is None or stage_inode is None:
        raise CompanyFactsIntakeError(f"Company Facts {label} descriptor is unavailable")
    opened = os.fstat(stage_fd)
    if not stat.S_ISDIR(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
        stage_device, stage_inode,
    ):
        raise CompanyFactsIntakeError(f"Company Facts {label} descriptor identity changed")
    try:
        bound = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise CompanyFactsIntakeError(f"Company Facts {label} was renamed") from exc
    if stat.S_ISLNK(bound.st_mode) or (bound.st_dev, bound.st_ino) != (
        stage_device, stage_inode,
    ):
        raise CompanyFactsIntakeError(f"Company Facts {label} was rebound")


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
    lane: _CompanyFactsLane | None = None,
) -> _PreparedGeneration:
    if lane is not None:
        _assert_lane_path_identity(lane)
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
    stage_fd: int | None = None
    stage_device: int | None = None
    stage_inode: int | None = None
    try:
        with _open_companyfacts_directory(root, create=True, lane=lane) as root_fd:
            try:
                os.mkdir(stage_name, mode=0o700, dir_fd=root_fd)
            except FileExistsError as exc:
                raise CompanyFactsIntakeError("Company Facts generation stage collision") from exc
            _fsync_held_directory(root_fd, stage)
            stage_fd = _open_verified_directory_component(
                root_fd, stage_name, create=False, label=str(stage),
            )
            stage_stat = os.fstat(stage_fd)
            stage_device, stage_inode = stage_stat.st_dev, stage_stat.st_ino
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
        with _open_companyfacts_directory(root, lane=lane) as stage_parent_fd:
            _assert_stage_inode_binding(
                stage_parent_fd, stage_name, stage_fd, stage_device, stage_inode,
                label="sealed generation stage",
            )
            assert stage_fd is not None
            _write_new_regular_bytes_at(
                stage_fd, "source_manifest.parquet", manifest_body,
                label="staged source manifest",
            )
            _write_new_regular_bytes_at(
                stage_fd, "coverage.parquet", coverage_body, label="staged coverage",
            )
            manifest_body = _read_regular_bytes_at(
                stage_fd, "source_manifest.parquet", label="staged source manifest",
                max_bytes=MAX_GENERATION_FILE_BYTES,
                expected_byte_length=len(manifest_body),
            )
            coverage_body = _read_regular_bytes_at(
                stage_fd, "coverage.parquet", label="staged coverage",
                max_bytes=MAX_GENERATION_FILE_BYTES,
                expected_byte_length=len(coverage_body),
            )
            assert manifest_body is not None and coverage_body is not None
            _fsync_held_directory(stage_fd, stage)
            _assert_stage_inode_binding(
                stage_parent_fd, stage_name, stage_fd, stage_device, stage_inode,
                label="sealed generation stage",
            )
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
        if lane is not None:
            _assert_lane_path_identity(lane)
        return _PreparedGeneration(
            descriptor=descriptor, stage_path=stage, stage_fd=stage_fd,
            stage_device=stage_device, stage_inode=stage_inode,
        )
    except Exception:
        _discard_stage(
            root, stage, ignore_errors=True, lane=lane, stage_fd=stage_fd,
            stage_device=stage_device, stage_inode=stage_inode,
        )
        if stage_fd is not None:
            os.close(stage_fd)
        raise


def _generation_paths(
    root: Path, descriptor: Mapping[str, Any], *, lane: _CompanyFactsLane | None = None,
) -> tuple[Path, Path]:
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
        with _open_companyfacts_directory(root, ("generations",), lane=lane) as generations_fd:
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


def _validate_generation_files(
    root: Path, descriptor: Mapping[str, Any], *, lane: _CompanyFactsLane | None = None,
) -> tuple[Path, Path]:
    source_path, coverage_path = _generation_paths(root, descriptor, lane=lane)
    digest = str(descriptor["generation_id"]).rsplit(":", 1)[-1]
    with _open_companyfacts_directory(root, ("generations", digest), lane=lane) as generation_fd:
        _generation_bodies_at(generation_fd, descriptor)
    return source_path, coverage_path


def _generation_bodies_at(
    generation_fd: int, descriptor: Mapping[str, Any],
) -> tuple[bytes, bytes]:
    bodies: dict[str, bytes] = {}
    for key, name in (
        ("source_manifest", "source_manifest.parquet"),
        ("coverage", "coverage.parquet"),
    ):
        expected = descriptor.get(key)
        expected_length = expected.get("byte_length") if isinstance(expected, Mapping) else None
        if (
            isinstance(expected_length, bool)
            or not isinstance(expected_length, int)
            or expected_length < 1
            or expected_length > MAX_GENERATION_FILE_BYTES
        ):
            raise CompanyFactsIntakeError(
                f"committed Company Facts {key} has an invalid exact length"
            )
        body = _read_regular_bytes_at(
            generation_fd, name, label=f"committed {key} generation file",
            max_bytes=MAX_GENERATION_FILE_BYTES,
            expected_byte_length=expected_length,
        )
        assert body is not None
        if _bytes_receipt(body) != {
            "sha256": expected.get("sha256"), "byte_length": expected_length,
        }:
            raise CompanyFactsIntakeError(
                f"committed Company Facts {key} exact-byte receipt mismatch"
            )
        bodies[key] = body
    return bodies["source_manifest"], bodies["coverage"]


def _generation_bodies(
    root: Path, descriptor: Mapping[str, Any], *, lane: _CompanyFactsLane | None = None,
) -> tuple[bytes, bytes]:
    """Return exact, receipt-validated generation bytes through a no-follow chain."""
    _generation_paths(root, descriptor, lane=lane)
    digest = str(descriptor["generation_id"]).rsplit(":", 1)[-1]
    with _open_companyfacts_directory(root, ("generations", digest), lane=lane) as generation_fd:
        return _generation_bodies_at(generation_fd, descriptor)


def _install_generation(
    root: Path, prepared: _PreparedGeneration, *, lane: _CompanyFactsLane | None = None,
) -> None:
    if lane is not None:
        _assert_lane_path_identity(lane)
    digest = str(prepared.descriptor["generation_id"]).rsplit(":", 1)[-1]
    if prepared.stage_path is None:
        try:
            with _open_companyfacts_directory(root, ("generations",), lane=lane) as generations_fd:
                try:
                    target_fd = os.open(
                        digest,
                        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                        | getattr(os, "O_NOFOLLOW", 0),
                        dir_fd=generations_fd,
                    )
                except OSError as exc:
                    raise CompanyFactsIntakeError(
                        "Company Facts committed generation cannot be held securely"
                    ) from exc
                try:
                    target_stat = os.fstat(target_fd)
                    if not stat.S_ISDIR(target_stat.st_mode):
                        raise CompanyFactsIntakeError(
                            "Company Facts committed generation is not a directory"
                        )
                    prepared.stage_fd = target_fd
                    target_fd = None
                    prepared.stage_device = target_stat.st_dev
                    prepared.stage_inode = target_stat.st_ino
                    prepared.installed_name = digest
                finally:
                    if target_fd is not None:
                        os.close(target_fd)
            _hold_prepared_generation_files(prepared)
            _assert_prepared_generation_binding(root, prepared, lane=lane)
        except Exception:
            _release_prepared_stage(prepared)
            raise
        return
    _generation_paths(root, prepared.descriptor, lane=lane)
    stage = prepared.stage_path
    stage_moved = False
    try:
        with _open_companyfacts_directory(root, create=True, lane=lane) as root_fd:
            stage_name = _assert_prepared_stage_binding(root, root_fd, prepared)
            with _open_companyfacts_directory(
                root, ("generations",), create=True, lane=lane,
            ) as generations_fd:
                try:
                    target_fd = os.open(
                        digest,
                        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                        dir_fd=generations_fd,
                    )
                except FileNotFoundError:
                    target_fd = None
                if target_fd is not None:
                    try:
                        target_stat = os.fstat(target_fd)
                        if not stat.S_ISDIR(target_stat.st_mode):
                            raise CompanyFactsIntakeError(
                                "Company Facts committed generation is not a directory"
                            )
                        _generation_bodies_at(target_fd, prepared.descriptor)
                        _discard_stage(
                            root, stage, lane=lane, stage_fd=prepared.stage_fd,
                            stage_device=prepared.stage_device, stage_inode=prepared.stage_inode,
                        )
                        if prepared.stage_fd is not None:
                            os.close(prepared.stage_fd)
                        prepared.stage_fd = target_fd
                        target_fd = None
                        prepared.stage_device = target_stat.st_dev
                        prepared.stage_inode = target_stat.st_ino
                        prepared.stage_path = None
                        prepared.installed_name = digest
                    finally:
                        if target_fd is not None:
                            os.close(target_fd)
                else:
                    if lane is not None:
                        _assert_lane_path_identity(lane)
                    stage_name = _assert_prepared_stage_binding(root, root_fd, prepared)
                    os.replace(stage_name, digest, src_dir_fd=root_fd, dst_dir_fd=generations_fd)
                    stage_moved = True
                    prepared.stage_path = None
                    prepared.installed_name = digest
                    installed = os.stat(digest, dir_fd=generations_fd, follow_symlinks=False)
                    if stat.S_ISLNK(installed.st_mode) or (installed.st_dev, installed.st_ino) != (
                        prepared.stage_device, prepared.stage_inode,
                    ):
                        raise CompanyFactsIntakeError(
                            "Company Facts installed generation inode is detached from sealed stage"
                        )
                    _fsync_held_directory(generations_fd, root / "generations")
        if lane is not None:
            _assert_lane_path_identity(lane)
        _hold_prepared_generation_files(prepared)
        _assert_prepared_generation_binding(root, prepared, lane=lane)
    except Exception:
        if not stage_moved and prepared.stage_path is not None:
            _discard_stage(
                root, stage, ignore_errors=True, lane=lane, stage_fd=prepared.stage_fd,
                stage_device=prepared.stage_device, stage_inode=prepared.stage_inode,
            )
        _release_prepared_stage(prepared)
        raise


def _assert_prepared_stage_binding(
    root: Path, root_fd: int, prepared: _PreparedGeneration,
) -> str:
    stage = prepared.stage_path
    if stage is None or prepared.stage_fd is None:
        raise CompanyFactsIntakeError("Company Facts sealed generation stage descriptor is unavailable")
    parts = _relative_parts(root, stage)
    if len(parts) != 1 or not parts[0].startswith(".generation-stage-"):
        raise CompanyFactsIntakeError("Company Facts generation stage path is not root-bound")
    _assert_stage_inode_binding(
        root_fd, parts[0], prepared.stage_fd, prepared.stage_device, prepared.stage_inode,
        label="sealed generation stage",
    )
    return parts[0]


def _assert_prepared_generation_binding(
    root: Path, prepared: _PreparedGeneration, *, lane: _CompanyFactsLane | None,
) -> None:
    name = prepared.installed_name
    if name is None:
        raise CompanyFactsIntakeError("Company Facts installed generation name is unavailable")
    with _open_companyfacts_directory(root, ("generations",), lane=lane) as generations_fd:
        _assert_stage_inode_binding(
            generations_fd, name, prepared.stage_fd,
            prepared.stage_device, prepared.stage_inode,
            label="installed generation",
        )
    assert prepared.stage_fd is not None
    expected_names = {"source_manifest.parquet", "coverage.parquet"}
    if set(prepared.generation_files) != expected_names:
        raise CompanyFactsIntakeError(
            "Company Facts installed generation child descriptors are unavailable"
        )
    for key, name in (
        ("source_manifest", "source_manifest.parquet"),
        ("coverage", "coverage.parquet"),
    ):
        descriptor, fingerprint = prepared.generation_files[name]
        opened = os.fstat(descriptor)
        if _regular_metadata_fingerprint(opened) != fingerprint:
            raise CompanyFactsIntakeError(
                f"Company Facts installed {name} descriptor metadata changed"
            )
        _assert_prepared_generation_file_binding(prepared, name, descriptor)
        expected = prepared.descriptor[key]
        body = _read_regular_descriptor_bytes(
            descriptor, label=f"installed {key} generation file",
            max_bytes=MAX_GENERATION_FILE_BYTES,
            expected_byte_length=expected["byte_length"],
        )
        if _bytes_receipt(body) != {
            "sha256": expected.get("sha256"), "byte_length": expected.get("byte_length"),
        }:
            raise CompanyFactsIntakeError(
                f"committed Company Facts {key} exact-byte receipt mismatch"
            )
    # Reassert both names and immutable metadata after both reads. This catches
    # a swap or in-place mutation of the first child while the second is read.
    for name, (descriptor, fingerprint) in prepared.generation_files.items():
        if _regular_metadata_fingerprint(os.fstat(descriptor)) != fingerprint:
            raise CompanyFactsIntakeError(
                f"Company Facts installed {name} descriptor metadata changed"
            )
        _assert_prepared_generation_file_binding(prepared, name, descriptor)


def _assert_prepared_generation_file_binding(
    prepared: _PreparedGeneration, name: str, descriptor: int,
) -> None:
    if prepared.stage_fd is None:
        raise CompanyFactsIntakeError("Company Facts installed generation descriptor is unavailable")
    opened = os.fstat(descriptor)
    try:
        bound = os.stat(name, dir_fd=prepared.stage_fd, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise CompanyFactsIntakeError(
            f"Company Facts installed {name} was renamed"
        ) from exc
    if stat.S_ISLNK(bound.st_mode) or (bound.st_dev, bound.st_ino) != (
        opened.st_dev, opened.st_ino,
    ):
        raise CompanyFactsIntakeError(f"Company Facts installed {name} was rebound")


def _hold_prepared_generation_files(prepared: _PreparedGeneration) -> None:
    if prepared.stage_fd is None:
        raise CompanyFactsIntakeError("Company Facts installed generation descriptor is unavailable")
    if prepared.generation_files:
        raise CompanyFactsIntakeError("Company Facts installed child descriptors already exist")
    opened: dict[str, tuple[int, tuple[Any, ...]]] = {}
    try:
        for name in ("source_manifest.parquet", "coverage.parquet"):
            descriptor: int | None = os.open(
                name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=prepared.stage_fd,
            )
            try:
                metadata = os.fstat(descriptor)
                if not stat.S_ISREG(metadata.st_mode):
                    raise CompanyFactsIntakeError(
                        f"Company Facts installed {name} is not a regular file"
                    )
                opened[name] = (descriptor, _regular_metadata_fingerprint(metadata))
                descriptor = None
            finally:
                if descriptor is not None:
                    os.close(descriptor)
        prepared.generation_files = opened
    except Exception:
        for descriptor, _fingerprint in opened.values():
            os.close(descriptor)
        raise


def _release_prepared_stage(prepared: _PreparedGeneration) -> None:
    for descriptor, _fingerprint in prepared.generation_files.values():
        os.close(descriptor)
    prepared.generation_files = {}
    if prepared.stage_fd is not None:
        os.close(prepared.stage_fd)
    prepared.stage_fd = None
    prepared.stage_device = None
    prepared.stage_inode = None
    prepared.stage_path = None
    prepared.installed_name = None


def _discard_prepared_generation(
    prepared: _PreparedGeneration | None, *, lane: _CompanyFactsLane | None = None,
) -> None:
    """Remove an unpublished stage after budget/publish failure."""
    if prepared is None:
        return
    try:
        if prepared.stage_path is not None:
            root = prepared.stage_path.parent
            _discard_stage(
                root, prepared.stage_path, ignore_errors=True, lane=lane,
                stage_fd=prepared.stage_fd, stage_device=prepared.stage_device,
                stage_inode=prepared.stage_inode,
            )
    finally:
        _release_prepared_stage(prepared)


def _discard_stage(
    root: Path, stage: Path, *, ignore_errors: bool = False,
    lane: _CompanyFactsLane | None = None,
    stage_fd: int | None = None, stage_device: int | None = None,
    stage_inode: int | None = None,
) -> None:
    """Delete only a no-follow, root-owned staging directory and its regular files."""
    try:
        parts = _relative_parts(root, stage)
        if len(parts) != 1 or not parts[0].startswith(".generation-stage-"):
            raise CompanyFactsIntakeError("Company Facts stage path is not root-bound")
        with _open_companyfacts_directory(root, lane=lane) as root_fd:
            opened_here = stage_fd is None
            if stage_fd is None:
                try:
                    stage_fd = os.open(
                        parts[0],
                        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                        dir_fd=root_fd,
                    )
                except FileNotFoundError:
                    return
            else:
                metadata = os.fstat(stage_fd)
                if (
                    stage_device is None
                    or stage_inode is None
                    or not stat.S_ISDIR(metadata.st_mode)
                    or (metadata.st_dev, metadata.st_ino) != (stage_device, stage_inode)
                ):
                    raise CompanyFactsIntakeError("Company Facts cleanup stage identity changed")
                try:
                    bound = os.stat(parts[0], dir_fd=root_fd, follow_symlinks=False)
                except FileNotFoundError:
                    return
                if stat.S_ISLNK(bound.st_mode) or (bound.st_dev, bound.st_ino) != (
                    stage_device, stage_inode,
                ):
                    raise CompanyFactsIntakeError("Company Facts cleanup stage was rebound")
            try:
                for name in os.listdir(stage_fd):
                    metadata = os.stat(name, dir_fd=stage_fd, follow_symlinks=False)
                    if not stat.S_ISREG(metadata.st_mode):
                        raise CompanyFactsIntakeError("Company Facts stage contains unsafe non-file entry")
                    os.unlink(name, dir_fd=stage_fd)
            finally:
                if opened_here:
                    os.close(stage_fd)
            os.rmdir(parts[0], dir_fd=root_fd)
    except Exception:
        if not ignore_errors:
            raise


def _publish_generation(
    *, root: Path, receipt_path: Path, receipt: Mapping[str, Any], prepared: _PreparedGeneration,
    signer: CompanyFactsSigner, head_guard: CompanyFactsHeadGuard,
    expected_witness: Mapping[str, Any] | None, expected_witness_token: str | None,
    expected_pointer: bytes | None, lane: _CompanyFactsLane | None = None,
) -> None:
    """Seal artifacts, CAS the external head, then advance the local selector."""
    if lane is not None:
        _assert_lane_path_identity(lane)
    _install_generation(root, prepared, lane=lane)
    _assert_prepared_generation_binding(root, prepared, lane=lane)
    receipt_body = _canonical_bytes(dict(receipt)) + b"\n"
    receipt_digest = str(receipt["receipt_id"]).rsplit(":", 1)[-1]
    immutable_relative = f"receipts/{receipt_digest}.json"
    immutable_path = root / immutable_relative
    _write_immutable_bytes(immutable_path, receipt_body, root=root, lane=lane)
    with _open_companyfacts_directory(root, ("receipts",), lane=lane) as receipts_fd:
        held_receipt = _hold_regular_file_at(
            receipts_fd, f"{receipt_digest}.json", label="immutable receipt",
        )
    try:
        def assert_prior_chain() -> None:
            previous = receipt.get("previous_receipt")
            if previous is None:
                return
            if not isinstance(previous, Mapping):
                raise CompanyFactsIntakeError(
                    "Company Facts immutable predecessor reference is malformed"
                )
            chain = _walk_receipt_chain(root, previous, signer=signer, lane=lane)
            if int(chain[0]["sequence"]) + 1 != int(receipt["sequence"]):
                raise CompanyFactsIntakeError(
                    "Company Facts immutable predecessor sequence changed before publish"
                )

        def assert_receipt() -> dict[str, Any]:
            if lane is not None:
                _assert_lane_path_identity(lane)
            with _open_companyfacts_directory(root, ("receipts",), lane=lane) as current_receipts_fd:
                return _assert_held_regular_file_binding(
                    held_receipt, current_parent_fd=current_receipts_fd,
                    expected_body=receipt_body, max_bytes=MAX_RECEIPT_BYTES,
                    label="immutable receipt",
                )

        _assert_prepared_generation_binding(root, prepared, lane=lane)
        assert_prior_chain()
        # The first retained-FD read must bind both exact length and exact SHA to
        # the canonical signed bytes; length alone is not publication evidence.
        receipt_file = assert_receipt()
        witness = _head_witness(receipt=receipt, receipt_file=receipt_file, signer=signer)
        # This is the authoritative exact-predecessor CAS. It must precede the
        # local pointer. Recheck both immutable namespaces immediately before it.
        if lane is not None:
            _assert_lane_path_identity(lane)
        _assert_prepared_generation_binding(root, prepared, lane=lane)
        assert_prior_chain()
        receipt_file = assert_receipt()
        head_guard.advance(
            expected=expected_witness,
            expected_token=expected_witness_token,
            candidate=witness,
        )
        # The remote CAS and local namespace cannot be one atomic transaction.
        # A mutation during CAS may leave an external-head-ahead recovery state,
        # but must never advance the local selector.
        _assert_prepared_generation_binding(root, prepared, lane=lane)
        assert_prior_chain()
        receipt_file = assert_receipt()
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
        # Make full-history and new-receipt validation the last operations before
        # selector publication. Every prior receipt revalidates its generation.
        _assert_prepared_generation_binding(root, prepared, lane=lane)
        assert_prior_chain()
        assert_receipt()
        _atomic_write_bytes(
            receipt_path, pointer_body, expected_previous=expected_pointer, root=root, lane=lane,
        )
        if _file_receipt(
            receipt_path, root=root, lane=lane, max_bytes=MAX_POINTER_BYTES,
            expected_byte_length=len(pointer_body),
        ) != _bytes_receipt(pointer_body):
            raise CompanyFactsIntakeError("Company Facts current pointer read-back mismatch")
        _assert_prepared_generation_binding(root, prepared, lane=lane)
        assert_prior_chain()
        assert_receipt()
        _release_prepared_stage(prepared)
    finally:
        _release_held_regular_file(held_receipt)


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
        # Retain the exact identity-checked manifest so the object read can be
        # cross-bound to its SEC envelope before this CIK receives network
        # authority.  The smaller fields above remain the receipt-safe view.
        "manifest_record": dict(record),
    }


def _strict_anchor_sec_envelope(record: Mapping[str, Any], body: bytes) -> None:
    """Bind exact retained complete-submission bytes to every SEC identity axis.

    Manifest self-hashes only prove that a row is internally immutable.  They
    do not prove that a re-authored row describes the retained SEC object.  This
    parser intentionally does not depend on the filing collector's permissive
    SGML parser: required identity fields must each occupy one unique whole
    header line and agree with the top-level SEC-DOCUMENT line, the primary
    DOCUMENT TYPE, and the manifest coordinates.
    """
    if not isinstance(body, bytes):
        raise CompanyFactsAnchorVerificationError("anchor retained object is not bytes")
    try:
        validate_manifest_identity(record)
        validate_manifest_content_binding(record)
    except (ManifestIdentityError, TypeError, ValueError) as exc:
        raise CompanyFactsAnchorVerificationError(
            "anchor manifest content identity is invalid"
        ) from exc

    issuer = record.get("issuer") if isinstance(record.get("issuer"), Mapping) else {}
    filing = record.get("filing") if isinstance(record.get("filing"), Mapping) else {}
    document = record.get("document") if isinstance(record.get("document"), Mapping) else {}
    try:
        cik = canonical_cik(issuer.get("cik"))
    except (CompanyFactsDeferred, CompanyFactsIntakeError) as exc:
        raise CompanyFactsAnchorVerificationError("anchor manifest CIK is invalid") from exc
    accession = str(filing.get("accession") or "")
    form = str(filing.get("form") or "").strip().upper()
    if (
        record.get("source_system") != "sec_edgar"
        or issuer.get("issuer_id") != f"sec:cik:{cik}"
        or len(accession) != 20
        or accession[10:11] != "-"
        or accession[13:14] != "-"
        or not (accession[:10] + accession[11:13] + accession[14:]).isdigit()
        or accession[:10] != cik
        or not form
    ):
        raise CompanyFactsAnchorVerificationError("anchor manifest SEC identity is not cross-bound")
    if (
        record.get("source_id") != f"{accession}:0:complete-submission.txt"
        or document.get("document_role") != "complete_submission"
        or document.get("document_name") != "complete-submission.txt"
        or str(document.get("sequence")) != "0"
        or str(document.get("document_type") or "").strip().upper() != form
    ):
        raise CompanyFactsAnchorVerificationError(
            "anchor manifest source/document identity is not cross-bound"
        )
    expected_url = (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}.txt"
    )
    if document.get("canonical_url") != expected_url:
        raise CompanyFactsAnchorVerificationError(
            "anchor manifest URL/accession identity is not cross-bound"
        )

    lines = [line.strip() for line in body.splitlines()]
    document_markers = [index for index, line in enumerate(lines) if line.upper() == b"<DOCUMENT>"]
    if not document_markers:
        raise CompanyFactsAnchorVerificationError("anchor SEC envelope has no DOCUMENT block")
    header = lines[:document_markers[0]]

    def unique_header_value(*prefixes: bytes, label: str) -> bytes:
        values: list[bytes] = []
        upper_prefixes = tuple(prefix.upper() for prefix in prefixes)
        for line in header:
            upper = line.upper()
            for prefix, upper_prefix in zip(prefixes, upper_prefixes):
                if upper.startswith(upper_prefix):
                    values.append(line[len(prefix):].strip())
                    break
        if len(values) != 1 or not values[0]:
            raise CompanyFactsAnchorVerificationError(
                f"anchor SEC envelope requires one unique {label} whole line"
            )
        return values[0]

    top_values: list[bytes] = []
    top_prefix = b"<SEC-DOCUMENT>"
    for line in lines:
        if line.upper().startswith(top_prefix):
            value = line[len(top_prefix):]
            # SEC sometimes suffixes the top filename with a colon and metadata.
            top_values.append(value.split(b":", 1)[0].strip())
    if len(top_values) != 1:
        raise CompanyFactsAnchorVerificationError(
            "anchor SEC envelope requires one unique SEC-DOCUMENT whole line"
        )
    expected_filename = f"{accession}.txt".encode("ascii")
    if top_values[0] != expected_filename:
        raise CompanyFactsAnchorVerificationError("anchor SEC-DOCUMENT/accession mismatch")

    header_accession = unique_header_value(
        b"<ACCESSION-NUMBER>", b"ACCESSION NUMBER:", label="accession",
    )
    header_cik = unique_header_value(
        b"<CENTRAL-INDEX-KEY>", b"CENTRAL INDEX KEY:", label="CIK",
    )
    header_form = unique_header_value(
        b"<CONFORMED-SUBMISSION-TYPE>", b"CONFORMED SUBMISSION TYPE:", label="form",
    )
    if header_accession != accession.encode("ascii"):
        raise CompanyFactsAnchorVerificationError("anchor SEC header/accession mismatch")
    if header_cik != cik.encode("ascii"):
        raise CompanyFactsAnchorVerificationError("anchor SEC header/CIK mismatch")
    try:
        observed_form = header_form.decode("ascii").strip().upper()
    except UnicodeDecodeError as exc:
        raise CompanyFactsAnchorVerificationError("anchor SEC header form is not ASCII") from exc
    if observed_form != form:
        raise CompanyFactsAnchorVerificationError("anchor SEC header/form mismatch")

    first_document = lines[document_markers[0] + 1:]
    try:
        first_close = next(
            index for index, line in enumerate(first_document) if line.upper() == b"</DOCUMENT>"
        )
    except StopIteration as exc:
        raise CompanyFactsAnchorVerificationError("anchor primary DOCUMENT block is unterminated") from exc
    type_prefix = b"<TYPE>"
    type_values = [
        line[len(type_prefix):].strip()
        for line in first_document[:first_close]
        if line.upper().startswith(type_prefix)
    ]
    if len(type_values) != 1:
        raise CompanyFactsAnchorVerificationError(
            "anchor primary DOCUMENT requires one unique TYPE whole line"
        )
    try:
        primary_form = type_values[0].decode("ascii").strip().upper()
    except UnicodeDecodeError as exc:
        raise CompanyFactsAnchorVerificationError("anchor primary TYPE is not ASCII") from exc
    if primary_form != form:
        raise CompanyFactsAnchorVerificationError("anchor primary TYPE/form mismatch")


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
            expected_byte_length=binding["byte_length"],
            max_byte_length=min(
                remaining_byte_budget
                if remaining_byte_budget is not None
                else HARD_MAX_RUN_BYTES,
                HARD_MAX_RUN_BYTES,
            ),
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
    manifest_record = anchor.get("manifest_record")
    if not isinstance(manifest_record, Mapping):
        raise CompanyFactsAnchorVerificationError("anchor manifest record is unavailable")
    _strict_anchor_sec_envelope(manifest_record, body)
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
    store: Any, object_key: object, content_sha256: object, *,
    expected_byte_length: int, max_byte_length: int,
    deadline: float | None, monotonic: Callable[[], float],
) -> Any:
    """Bound one uncooperative store read without allowing it to consume the run.

    Content stores expose no universal per-call timeout. The read is therefore
    isolated in a daemon thread and its late result is discarded. Python cannot
    cancel the backend call, so this is a wall-clock isolation boundary, not a
    claim that late backend resource use is cancelled. The mandatory bounded
    strict-read capability separately prevents a declared-length mismatch from
    causing an unbounded body allocation.
    """
    reader = getattr(store, "get_verified_strict_bounded", None)
    if not callable(reader):
        raise CompanyFactsIntakeError(
            "Company Facts source store lacks bounded strict-read capability"
        )

    def bounded_read() -> Any:
        return reader(
            object_key, content_sha256,
            expected_byte_length=expected_byte_length,
            max_byte_length=max_byte_length,
        )

    if deadline is None:
        return bounded_read()
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise CompanyFactsRunBudgetExceeded("Company Facts retention verification exceeded run deadline")
    completed = threading.Event()
    result: dict[str, Any] = {}

    def read() -> None:
        try:
            result["body"] = bounded_read()
        except BaseException as exc:  # noqa: BLE001 - forwarded into fail-closed caller
            result["error"] = exc
        finally:
            completed.set()

    threading.Thread(target=read, name="companyfacts-source-read", daemon=True).start()
    if not completed.wait(remaining):
        raise CompanyFactsRunBudgetExceeded("Company Facts retention verification read exceeded remaining run deadline")
    if monotonic() > deadline:
        raise CompanyFactsRunBudgetExceeded("Company Facts retention verification exceeded run deadline")
    error = result.get("error")
    if isinstance(error, BaseException):
        raise error
    return result.get("body")


def _put_verified_before_deadline(
    store: Any, raw: bytes, *, media_type: str,
    deadline: float | None, monotonic: Callable[[], float],
) -> Any:
    """Isolate one immutable source admission inside the remaining run time.

    Python cannot cancel the backend write/readback after timeout. A late
    completion is therefore discarded and may leave only a content-addressed
    orphan; no manifest, receipt, external head, or local pointer can derive
    from that late result.
    """
    writer = getattr(store, "put_verified", None)
    if not callable(writer):
        raise CompanyFactsIntakeError("Company Facts source store cannot admit verified bytes")

    def put() -> Any:
        return writer(raw, media_type=media_type)

    if deadline is None:
        return put()
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise CompanyFactsRunBudgetExceeded(
            "Company Facts source admission exceeded run deadline"
        )
    completed = threading.Event()
    result: dict[str, Any] = {}

    def write() -> None:
        try:
            result["receipt"] = put()
        except BaseException as exc:  # noqa: BLE001 - forwarded fail closed
            result["error"] = exc
        finally:
            completed.set()

    threading.Thread(target=write, name="companyfacts-source-admission", daemon=True).start()
    if not completed.wait(remaining):
        raise CompanyFactsRunBudgetExceeded(
            "Company Facts source admission exceeded remaining run deadline"
        )
    if monotonic() > deadline:
        raise CompanyFactsRunBudgetExceeded(
            "Company Facts source admission exceeded run deadline"
        )
    error = result.get("error")
    if isinstance(error, BaseException):
        raise error
    return result.get("receipt")


def _verify_selected_source_objects(
    source_records: Sequence[Mapping[str, Any]], *, source_stores: Mapping[str, Any],
    deadline: float | None = None, monotonic: Callable[[], float] = time.monotonic,
    byte_observer: Callable[[int], None] | None = None,
    remaining_byte_budget: int | None = None,
) -> None:
    """Require each *selected* retained source object to remain exact and readable."""
    consumed = 0
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
        if getattr(store, "store_id", None) != store_id:
            raise CompanyFactsIntakeError("Company Facts selected source store identity is detached")
        if getattr(store, "backend", None) != storage.get("backend"):
            raise CompanyFactsIntakeError("Company Facts selected source store backend is detached")
        digest = content.get("content_sha256")
        byte_length = content.get("byte_length")
        if (
            isinstance(byte_length, bool)
            or not isinstance(byte_length, int)
            or byte_length < 1
            or byte_length > HARD_MAX_RESPONSE_BYTES
        ):
            raise CompanyFactsIntakeError(
                "Company Facts selected source declared length exceeds strict-read boundary"
            )
        remaining = (
            HARD_MAX_RESPONSE_BYTES
            if remaining_byte_budget is None
            else remaining_byte_budget - consumed
        )
        if remaining < 0 or byte_length > remaining:
            raise CompanyFactsRunBudgetExceeded(
                "Company Facts retention verification exceeds remaining run byte budget"
            )
        try:
            expected_key = object_key_for_sha256(digest)
        except (TypeError, ValueError) as exc:
            raise CompanyFactsIntakeError(
                "Company Facts selected source content digest is invalid"
            ) from exc
        if storage.get("object_key") != expected_key:
            raise CompanyFactsIntakeError(
                "Company Facts selected source object key is detached from its digest"
            )
        try:
            body = _get_verified_before_deadline(
                store, expected_key, digest,
                expected_byte_length=byte_length,
                max_byte_length=min(HARD_MAX_RESPONSE_BYTES, remaining),
                deadline=deadline, monotonic=monotonic,
            )
        except CompanyFactsRunBudgetExceeded:
            raise
        except CompanyFactsIntakeError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise CompanyFactsIntakeError("Company Facts selected source object verification failed") from exc
        if (
            not isinstance(body, bytes)
            or len(body) != byte_length
            or sha256(body).hexdigest() != digest
        ):
            raise CompanyFactsIntakeError("Company Facts selected source object is missing or mismatched")
        consumed += len(body)
        if byte_observer is not None:
            byte_observer(len(body))


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


def _receipt_reference(
    receipt: Mapping[str, Any], path: Path, *, root: Path,
    lane: _CompanyFactsLane | None = None,
) -> dict[str, Any]:
    relative = path.parent.name + "/" + path.name
    expected_body = _canonical_bytes(dict(receipt)) + b"\n"
    file_receipt = _file_receipt(
        path, root=root, lane=lane, max_bytes=MAX_RECEIPT_BYTES,
        expected_byte_length=len(expected_body),
    )
    if file_receipt != _bytes_receipt(expected_body):
        raise CompanyFactsIntakeError(
            "prior Company Facts receipt changed before predecessor binding"
        )
    return {
        "receipt_id": receipt["receipt_id"], "path": relative,
        **file_receipt,
    }


def _read_receipt_reference(
    root: Path, reference: Mapping[str, Any], *, signer: CompanyFactsSigner,
    lane: _CompanyFactsLane | None = None,
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
    expected_length = expected_file["byte_length"]
    if _file_receipt(
        path, root=root, lane=lane, max_bytes=MAX_RECEIPT_BYTES,
        expected_byte_length=expected_length,
    ) != expected_file:
        raise CompanyFactsIntakeError("immutable Company Facts receipt exact-byte mismatch")
    parts = _relative_parts(root, path)
    with _open_companyfacts_parent(root, parts, lane=lane) as (parent_fd, name):
        body = _read_regular_bytes_at(
            parent_fd, name, label="immutable receipt", max_bytes=MAX_RECEIPT_BYTES,
            expected_byte_length=expected_length,
        )
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
    _validate_generation_files(root, receipt["generation"], lane=lane)
    return dict(receipt)


def _load_receipt_generation(
    root: Path, receipt: Mapping[str, Any], *, lane: _CompanyFactsLane | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Authenticate one receipt's exact immutable generation and commitments."""
    source_body, coverage_body = _generation_bodies(root, receipt["generation"], lane=lane)
    source_records = _records(_read_ledger_bytes(source_body, _SOURCE_MANIFEST_COLUMNS, label="committed source manifest"))
    coverage_records = _records(_read_ledger_bytes(coverage_body, _COVERAGE_COLUMNS, label="committed coverage"))
    if _ledger_receipt(source_records) != receipt["companyfacts_manifest_ledger"]:
        raise CompanyFactsIntakeError("receipt/source manifest ordered-prefix mismatch")
    if _ledger_receipt(coverage_records) != receipt["coverage_ledger"]:
        raise CompanyFactsIntakeError("receipt/coverage ordered-prefix mismatch")
    return source_records, coverage_records


def _walk_receipt_chain(
    root: Path, current_reference: Mapping[str, Any], *, signer: CompanyFactsSigner,
    lane: _CompanyFactsLane | None = None,
) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    reference: Mapping[str, Any] | None = current_reference
    while reference is not None:
        if len(chain) >= MAX_RECEIPT_CHAIN_LENGTH:
            raise CompanyFactsIntakeError(
                "Company Facts receipt chain reached its hard checkpoint/compaction boundary"
            )
        receipt = _read_receipt_reference(root, reference, signer=signer, lane=lane)
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
    lane: _CompanyFactsLane | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    """Load only the generation selected by an authenticated immutable receipt chain."""
    if lane is not None:
        _assert_lane_path_identity(lane)
    try:
        with _open_companyfacts_directory(root, lane=lane) as root_fd:
            names = set(os.listdir(root_fd))
            if lane is None:
                immutable_history = any(
                    name in names for name in ("receipts", "generations")
                )
            else:
                immutable_history = bool(
                    os.listdir(lane.receipts_fd) or os.listdir(lane.generations_fd)
                )
            immutable_history = immutable_history or any(
                name.startswith(".generation-stage-") for name in names
            )
            pointer_parts = _relative_parts(root, receipt_path)
            with _open_companyfacts_parent(root, pointer_parts, lane=lane) as (parent_fd, pointer_name):
                pointer_body = _read_regular_bytes_at(
                    parent_fd, pointer_name, label="current pointer",
                    max_bytes=MAX_POINTER_BYTES, missing_ok=True,
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
    chain = _walk_receipt_chain(root, current_reference, signer=signer, lane=lane)
    receipt = chain[0]
    if (
        pointer["generation_id"] != receipt["generation"]["generation_id"]
        or pointer["published_at"] != receipt["published_at"]
    ):
        raise CompanyFactsIntakeError("Company Facts pointer is detached from immutable receipt")
    _validate_head_witness(head_witness, signer=signer)
    head_file = _file_receipt(
        root / str(pointer["receipt_path"]), root=root, lane=lane,
        max_bytes=MAX_RECEIPT_BYTES,
        expected_byte_length=pointer["receipt_byte_length"],
    )
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
        chained_sources, chained_coverage = _load_receipt_generation(
            root, chained_receipt, lane=lane,
        )
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
        self._run_byte_categories: dict[str, int] = {}
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

    def _consume_run_bytes(self, count: int, *, category: str) -> None:
        if not isinstance(count, int) or count < 0:
            raise CompanyFactsIntakeError("Company Facts stream reported invalid byte count")
        if category not in {
            "anchor_verification_bytes",
            "retention_verification_bytes",
            "sec_response_bytes",
            "source_store_write_reserved_bytes",
            "source_store_readback_reserved_bytes",
        }:
            raise CompanyFactsIntakeError("Company Facts byte accounting category is invalid")
        self._run_bytes += count
        self._run_byte_categories[category] = self._run_byte_categories.get(category, 0) + count
        if self._run_bytes > self.max_run_bytes:
            raise CompanyFactsRunBudgetExceeded("Company Facts run byte budget exhausted")

    def _observe_run_bytes(self, category: str) -> Callable[[int], None]:
        return lambda count: self._consume_run_bytes(count, category=category)

    def _reserve_source_admission_bytes(self, byte_length: int) -> None:
        if isinstance(byte_length, bool) or not isinstance(byte_length, int) or byte_length < 0:
            raise CompanyFactsIntakeError("Company Facts source admission length is invalid")
        reservation = byte_length * 2
        if reservation > self.max_run_bytes - self._run_bytes:
            raise CompanyFactsRunBudgetExceeded(
                "Company Facts source admission exceeds remaining run byte budget"
            )
        self._consume_run_bytes(
            byte_length, category="source_store_write_reserved_bytes",
        )
        self._consume_run_bytes(
            byte_length, category="source_store_readback_reserved_bytes",
        )

    def _run_byte_accounting_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "definition": RUN_BYTE_ACCOUNTING,
            "max_bytes": self.max_run_bytes,
            "anchor_verification_bytes": self._run_byte_categories.get(
                "anchor_verification_bytes", 0,
            ),
            "retention_verification_bytes": self._run_byte_categories.get(
                "retention_verification_bytes", 0,
            ),
            "sec_response_bytes": self._run_byte_categories.get("sec_response_bytes", 0),
            "source_store_write_reserved_bytes": self._run_byte_categories.get(
                "source_store_write_reserved_bytes", 0,
            ),
            "source_store_readback_reserved_bytes": self._run_byte_categories.get(
                "source_store_readback_reserved_bytes", 0,
            ),
            "total_bytes": self._run_bytes,
        }
        _validate_run_byte_accounting(record)
        return record

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
                    byte_observer=self._observe_run_bytes("sec_response_bytes"),
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
        self._run_byte_categories = {}
        with _companyfacts_publish_lease(root) as lane:
            _assert_lane_path_identity(lane)
            signer, head_guard = self._trust_context()
            witnessed_head, witnessed_token = head_guard.read()
            source_stores = self._source_stores()
            anchor_frame = _read_ledger(anchor_path, [
                "schema", "manifest_id", "source_system", "source_id", "issuer", "filing", "document",
                "retrieval", "storage", "rights", "privacy", "parser", "spans",
            ], max_bytes=MAX_ANCHOR_LEDGER_BYTES, parent_fd=lane.parent_fd)
            anchor_records = _records(anchor_frame)
            anchors = _complete_submission_anchor_candidates(anchor_records)
            existing_manifests, coverage_records, prior_receipt = _load_committed_bundle(
                root=root, receipt_path=receipt_path, anchor_records=anchor_records,
                signer=signer, head_witness=witnessed_head, lane=lane,
            )
            selection_as_of = _strict_utc(self._now_fn(), field="selection_as_of")
            retention_plan = _retention_audit_plan(existing_manifests, selection_as_of=selection_as_of)
            _verify_selected_source_objects(
                [record for record, _lane in retention_plan], source_stores=source_stores,
                deadline=self._run_deadline, monotonic=self._monotonic,
                byte_observer=self._observe_run_bytes("retention_verification_bytes"),
                remaining_byte_budget=self.max_run_bytes - self._run_bytes,
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
                byte_accounting = self._run_byte_accounting_record()
                return {"sec_companyfacts_intake": pd.DataFrame({
                    "status": [status], "eligible_ciks": [len(anchors)], "selected": [selected],
                    "retrieved": [int(counts["retrieved"])], "retry": [int(counts["retry"])],
                    "deferred": [int(counts["deferred"]) + deferred_queue_count],
                    "fresh_ciks": [population["fresh_ciks"]], "stale_ciks": [population["stale_ciks"]],
                    "pending_ciks": [population["pending_ciks"]],
                    "run_bytes": [byte_accounting["total_bytes"]],
                    "run_byte_accounting": [byte_accounting],
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
                        byte_observer=self._observe_run_bytes("anchor_verification_bytes"),
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
                    self._reserve_source_admission_bytes(len(raw))
                    receipt = _put_verified_before_deadline(
                        source_store, raw, media_type="application/json",
                        deadline=self._run_deadline, monotonic=self._monotonic,
                    )
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
                except CompanyFactsRunBudgetExceeded as exc:
                    # A server-supplied retry deadline is durable scheduling
                    # evidence. Admission/stream budget exhaustion has no such
                    # deadline and must abort before any publish.
                    if exc.retry_after_at is None:
                        raise
                    state, retry_deadline = _response_error_class(exc, attempted_at=attempted)
                    retry_after = _iso(retry_deadline)
                    error = f"{type(exc).__name__}: {exc}"[:500]
                    fresh_coverage.append(self._coverage_row(
                        item=item, attempted_at=attempted_at, state=state, error=error,
                        retry_after=retry_after, manifest=None,
                    ))
                    counts[state] += 1
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
                    lane=lane,
                )
                self._require_run_time()
                published_at = _strict_utc(self._now_fn(), field="published_at")
                previous_reference = None
                if prior_receipt is not None:
                    prior_digest = str(prior_receipt["receipt_id"]).rsplit(":", 1)[-1]
                    previous_reference = _receipt_reference(
                        prior_receipt, root / "receipts" / f"{prior_digest}.json", root=root,
                        lane=lane,
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
                    anchor_verifications=anchor_verifications,
                    run_byte_accounting=self._run_byte_accounting_record(), signer=signer,
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
                    with _open_companyfacts_parent(
                        root, _relative_parts(root, receipt_path), lane=lane,
                    ) as (parent_fd, name):
                        expected_pointer = _read_regular_bytes_at(
                            parent_fd, name, label="current pointer",
                            max_bytes=MAX_POINTER_BYTES,
                        )
                        assert expected_pointer is not None
                _publish_generation(
                    root=root, receipt_path=receipt_path, receipt=sealed_receipt, prepared=prepared,
                    signer=signer, head_guard=head_guard, expected_witness=witnessed_head,
                    expected_witness_token=witnessed_token, expected_pointer=expected_pointer,
                    lane=lane,
                )
            except Exception:
                _discard_prepared_generation(prepared, lane=lane)
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
    _validate_run_byte_accounting(receipt.get("run_byte_accounting"))
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
    accounting = receipt["run_byte_accounting"]
    admitted_bytes = sum(int(row["content"]["byte_length"]) for row in source_suffix)
    write_reserved = int(accounting["source_store_write_reserved_bytes"])
    readback_reserved = int(accounting["source_store_readback_reserved_bytes"])
    sec_response_bytes = int(accounting["sec_response_bytes"])
    if (
        write_reserved != readback_reserved
        or write_reserved < admitted_bytes
        or write_reserved > sec_response_bytes
        or admitted_bytes > sec_response_bytes
    ):
        raise CompanyFactsIntakeError(
            "receipt source admission byte accounting is detached from admitted evidence"
        )
    verified_anchor_bytes = sum(
        int(row["byte_length"])
        for row in anchor_verifications if row.get("status") == "verified"
    )
    declared_anchor_bytes = sum(int(row["byte_length"]) for row in anchor_verifications)
    accounted_anchor_bytes = int(accounting["anchor_verification_bytes"])
    if not verified_anchor_bytes <= accounted_anchor_bytes <= declared_anchor_bytes:
        raise CompanyFactsIntakeError(
            "receipt anchor verification byte accounting is detached"
        )
    expected_retention = _retention_verification(
        prior_source_records, selection_as_of=selection.to_pydatetime(),
        admitted_source_records=source_suffix,
    )
    if dict(receipt.get("retention_verification") or {}) != expected_retention:
        raise CompanyFactsIntakeError("receipt retention verification coverage is detached from its source history")
    prior_sources_by_id = {
        str(row["manifest_id"]): row for row in map(_native, prior_source_records)
    }
    checked_retention_ids = [
        *expected_retention["checked_current_manifest_ids"],
        *expected_retention["checked_historical_manifest_ids"],
    ]
    expected_retention_bytes = sum(
        int(prior_sources_by_id[manifest_id]["content"]["byte_length"])
        for manifest_id in checked_retention_ids
    )
    if int(accounting["retention_verification_bytes"]) != expected_retention_bytes:
        raise CompanyFactsIntakeError(
            "receipt retention verification byte accounting is detached"
        )


def _validate_run_byte_accounting(record: object) -> None:
    expected_fields = {
        "definition",
        "max_bytes",
        "anchor_verification_bytes",
        "retention_verification_bytes",
        "sec_response_bytes",
        "source_store_write_reserved_bytes",
        "source_store_readback_reserved_bytes",
        "total_bytes",
    }
    if not isinstance(record, Mapping) or set(record) != expected_fields:
        raise CompanyFactsIntakeError("Company Facts run byte accounting shape is invalid")
    if record.get("definition") != RUN_BYTE_ACCOUNTING:
        raise CompanyFactsIntakeError("Company Facts run byte accounting definition is invalid")
    numeric_fields = expected_fields - {"definition"}
    if any(
        isinstance(record.get(field), bool)
        or not isinstance(record.get(field), int)
        or int(record[field]) < 0
        for field in numeric_fields
    ):
        raise CompanyFactsIntakeError("Company Facts run byte accounting values are invalid")
    categories = (
        "anchor_verification_bytes",
        "retention_verification_bytes",
        "sec_response_bytes",
        "source_store_write_reserved_bytes",
        "source_store_readback_reserved_bytes",
    )
    if int(record["total_bytes"]) != sum(int(record[field]) for field in categories):
        raise CompanyFactsIntakeError("Company Facts run byte accounting total is detached")
    if int(record["total_bytes"]) > int(record["max_bytes"]):
        raise CompanyFactsIntakeError("Company Facts run byte accounting exceeds maximum")


def _coverage_receipt(
    *, selection_as_of: datetime, published_at: datetime, sequence: int,
    previous_receipt: Mapping[str, Any] | None, generation: Mapping[str, Any],
    anchor_records: Sequence[Mapping[str, Any]], source_records: Sequence[Mapping[str, Any]],
    coverage_records: Sequence[Mapping[str, Any]], eligible_ciks: int, queue: Sequence[Mapping[str, Any]], max_ciks: int,
    deferred_queue_count: int, skipped_fresh_count: int, counts: Mapping[str, int],
    queue_diagnostics: Mapping[str, Any], retention_verification: Mapping[str, Any],
    anchor_verifications: Sequence[Mapping[str, Any]],
    run_byte_accounting: Mapping[str, Any], signer: CompanyFactsSigner,
) -> dict[str, Any]:
    published_at = _strict_utc(published_at, field="published_at")
    selection_as_of = _strict_utc(selection_as_of, field="selection_as_of")
    anchors = _complete_submission_anchor_candidates(anchor_records)
    population = _coverage_population(anchors, coverage_records, as_of=published_at)
    _validate_run_byte_accounting(run_byte_accounting)
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
        "run_byte_accounting": dict(run_byte_accounting),
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
