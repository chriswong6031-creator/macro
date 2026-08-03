"""Authenticated, recoverable publication for canonical share-count ledgers.

This is deliberately a storage boundary, not a normalizer or a source reader.
Only a caller-validated canonical v2 ledger and its closed constant-size tail binding
may cross it.  The mutable local pointer is never authoritative: an HMAC signed
external head selects immutable receipt and ledger bytes that can reconstruct a
clean Actions workspace after a crash.  Protocol v2 uses signed binary-lifting
ancestor references: clean recovery reads only the selected receipt and ledger,
while a retained authenticated local high-water needs at most logarithmically
many skip-proof reads.  A replayed older (or forked) external head is never
allowed to roll it back.  A clean workspace has no such local high-water, so
this design does not claim that one mutable R2 head can defeat a credential-level
restore of that head and all externally immutable objects.
"""
from __future__ import annotations

import base64
import contextlib
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import time
from typing import Any, Callable, Iterator, Mapping, Protocol, Sequence
from urllib.parse import urlsplit


MAX_LEDGER_BYTES = 128 * 1024 * 1024
MAX_RECEIPT_BYTES = 4 * 1024 * 1024
MAX_POINTER_BYTES = 32 * 1024
MAX_HEAD_WITNESS_BYTES = 32 * 1024
MAX_PENDING_MARKER_BYTES = 512 * 1024
MAX_RECOVERY_CAPSULE_BYTES = 768 * 1024
MAX_PUBLISH_JOURNAL_BYTES = 512 * 1024
MAX_ANCESTOR_REFS = 64
MAX_RECEIPT_SEQUENCE = 1 << MAX_ANCESTOR_REFS
MAX_PREFIX_COUNT = 1_000_000
# The R2 client used by this lane has 15 second connect and 60 second read
# timeouts with adaptive retries.  Ten seconds was therefore a fictional
# deadline: one SDK call could legitimately outlive it.  This is one bounded
# end-to-end budget (lease + recovery + publication), with post-call checks for
# SDK calls that Python cannot hard-cancel.
PUBLICATION_TIMEOUT_SECONDS = 15.0 * 60.0
LEASE_TIMEOUT_SECONDS = PUBLICATION_TIMEOUT_SECONDS

RECEIPT_SCHEMA = "capital_structure.share_count_materialization_receipt/v2"
POINTER_SCHEMA = "capital_structure.share_count_current_pointer/v2"
WITNESS_V2_SCHEMA = "capital_structure.share_count_head_witness/v2"
WITNESS_V3_SCHEMA = "capital_structure.share_count_head_witness/v3"
WITNESS_SCHEMA = WITNESS_V2_SCHEMA
HEAD_GUARD_SCOPE_SCHEMA = "capital_structure.share_count_head_guard_scope/v1"
PENDING_SCHEMA = "capital_structure.share_count_publish_pending/v2"
RECOVERY_SCHEMA = "capital_structure.share_count_publish_recovery/v2"
JOURNAL_SCHEMA = "capital_structure.share_count_publish_journal/v1"
AUTH_SCHEME = "hmac-sha256/v1"
HEAD_GUARD_KEY = "capital_structure/share_counts/v2/current_head.json"
PENDING_NAME = ".share_count_publish_pending.json"
RECOVERY_NAME = ".share_count_publish_recovery.json"
JOURNAL_NAME = ".share_count_publish_journal.json"
POINTER_NAME = "current_receipt.json"
LOCK_NAME = ".share_count_publish.lock"

_HEX64 = re.compile(r"^[a-f0-9]{64}$")
_HEX32 = re.compile(r"^[a-f0-9]{32}$")
_RECEIPT_PREFIX = "receipt:cs-share-count-materialization-v2:"
_GENERATION_PREFIX = "generation:cs-share-count-materialization-v2:"
_POINTER_PREFIX = "pointer:cs-share-count-materialization-v2:"
_INPUT_BINDING_FIELDS = {
    "schema", "ledger_head_receipt_id", "ledger_sequence", "compiler_version",
    "materialized_at", "prefixes",
}
_PREFIX_LABELS = {"observations", "source_snapshots", "bridges", "source_manifests"}
_HEAD_SELECTION_FIELDS = {
    "sequence",
    "receipt_id",
    "receipt_sha256",
    "receipt_byte_length",
    "receipt_object_key",
    "generation_id",
    "ledger_sha256",
    "ledger_byte_length",
    "ledger_object_key",
    "published_at",
    "previous_receipt",
}


class ShareCountPublicationError(RuntimeError):
    """The immutable share-count publication boundary cannot prove safety."""


class ShareCountPublicationConflict(ShareCountPublicationError):
    """A competing publisher advanced the externally witnessed head."""


class ShareCountPublishIndeterminate(ShareCountPublicationError):
    """A failure after external CAS requires deterministic restart recovery."""


class ShareCountPublicationTooLarge(ShareCountPublicationError):
    """A bounded local or external object exceeded its declared ceiling."""


class _ShareCountPreCasFailure(ShareCountPublicationError):
    """The concrete guard proved that its conditional write was not invoked."""


class ShareCountSigner(Protocol):
    @property
    def key_id(self) -> str: ...

    def sign(self, payload: bytes) -> str: ...

    def verify(self, payload: bytes, signature: str, *, key_id: str) -> bool: ...

    def sign_head_v3(self, payload: bytes) -> str: ...

    def verify_head_v3(self, payload: bytes, signature: str, *, key_id: str) -> bool: ...

    def sign_journal(self, payload: bytes) -> str: ...

    def verify_journal(self, payload: bytes, signature: str, *, key_id: str) -> bool: ...


class HmacShareCountSigner:
    """Domain-separated HMAC signer for this publication lane only."""

    _DOMAIN = b"capital-structure-share-count-publication-head-v2\0"
    _HEAD_V3_DOMAIN = b"capital-structure-share-count-publication-head-v3\0"
    _JOURNAL_DOMAIN = b"capital-structure-share-count-publish-journal-v1\0"

    def __init__(self, secret: str | bytes, *, key_id: str) -> None:
        raw = secret.encode("utf-8") if isinstance(secret, str) else secret
        if not isinstance(raw, bytes) or len(raw) < 32:
            raise ValueError("share-count publication signing secret must contain at least 32 bytes")
        if not isinstance(key_id, str) or not key_id.strip():
            raise ValueError("share-count publication signer key_id is required")
        self._secret = raw
        self._key_id = key_id.strip()

    @property
    def key_id(self) -> str:
        return self._key_id

    def sign(self, payload: bytes) -> str:
        return hmac.new(self._secret, self._DOMAIN + payload, sha256).hexdigest()

    def verify(self, payload: bytes, signature: str, *, key_id: str) -> bool:
        return key_id == self.key_id and isinstance(signature, str) and hmac.compare_digest(
            self.sign(payload), signature,
        )

    def sign_head_v3(self, payload: bytes) -> str:
        return hmac.new(self._secret, self._HEAD_V3_DOMAIN + payload, sha256).hexdigest()

    def verify_head_v3(self, payload: bytes, signature: str, *, key_id: str) -> bool:
        return key_id == self.key_id and isinstance(signature, str) and hmac.compare_digest(
            self.sign_head_v3(payload), signature,
        )

    def sign_journal(self, payload: bytes) -> str:
        return hmac.new(self._secret, self._JOURNAL_DOMAIN + payload, sha256).hexdigest()

    def verify_journal(self, payload: bytes, signature: str, *, key_id: str) -> bool:
        return key_id == self.key_id and isinstance(signature, str) and hmac.compare_digest(
            self.sign_journal(payload), signature,
        )


class ShareCountHeadGuard(Protocol):
    """Durable CAS witness plus immutable external artifact recovery store."""

    def read(self) -> tuple[dict[str, Any] | None, str | None]: ...

    @property
    def guard_scope(self) -> Mapping[str, Any]: ...

    def advance(
        self, *, expected: Mapping[str, Any] | None, expected_token: str | None,
        candidate: Mapping[str, Any],
    ) -> None: ...

    def migrate_v2_to_v3(
        self, *, expected: Mapping[str, Any], expected_token: str,
        candidate: Mapping[str, Any],
    ) -> None: ...

    def seal_artifact(self, *, key: str, body: bytes, max_bytes: int) -> None: ...

    def read_artifact(self, *, key: str, max_bytes: int) -> bytes: ...


class InMemoryShareCountHeadGuard:
    """Deterministic test-only CAS and external immutable-object witness."""

    def __init__(
        self,
        signer: ShareCountSigner,
        *,
        account_id: str = "0" * 32,
        bucket: str = "in-memory-share-count-test",
    ) -> None:
        self._signer = signer
        self._guard_scope = _head_guard_scope(
            account_id=account_id,
            bucket=bucket,
            head_key=HEAD_GUARD_KEY,
        )
        self._witness: dict[str, Any] | None = None
        self._version = 0
        self._artifacts: dict[str, bytes] = {}

    @property
    def guard_scope(self) -> Mapping[str, Any]:
        return dict(self._guard_scope)

    def read(self) -> tuple[dict[str, Any] | None, str | None]:
        if self._witness is None:
            return None, None
        _validate_any_head_witness(
            self._witness,
            signer=self._signer,
            expected_scope=self._guard_scope,
        )
        return dict(self._witness), str(self._version)

    def advance(
        self, *, expected: Mapping[str, Any] | None, expected_token: str | None,
        candidate: Mapping[str, Any],
    ) -> None:
        observed, token = self.read()
        normalized = dict(expected) if expected is not None else None
        if observed is not None and observed.get("schema") == WITNESS_V3_SCHEMA:
            raise ShareCountPublicationError(
                "share-count v3 external head is a migration fence; publication is disabled",
            )
        if observed != normalized or token != expected_token:
            raise ShareCountPublicationConflict("share-count external head compare-and-swap conflict")
        _validate_head_transition(previous=observed, candidate=candidate, signer=self._signer)
        self._witness = dict(candidate)
        self._version += 1
        confirmed, _ = self.read()
        if confirmed != dict(candidate):
            raise ShareCountPublicationError("share-count external head read-back mismatch")

    def migrate_v2_to_v3(
        self,
        *,
        expected: Mapping[str, Any],
        expected_token: str,
        candidate: Mapping[str, Any],
    ) -> None:
        observed, token = self.read()
        if observed != dict(expected) or token != expected_token:
            raise ShareCountPublicationConflict(
                "share-count external head v3 migration compare-and-swap conflict",
            )
        _validate_head_migration(
            previous=expected,
            candidate=candidate,
            signer=self._signer,
            expected_scope=self._guard_scope,
        )
        self._witness = dict(candidate)
        self._version += 1
        confirmed, _ = self.read()
        if confirmed != dict(candidate):
            raise ShareCountPublicationError(
                "share-count external head v3 migration read-back mismatch",
            )

    def seal_artifact(self, *, key: str, body: bytes, max_bytes: int) -> None:
        _validate_external_artifact_key(key)
        if not isinstance(body, bytes) or not 1 <= len(body) <= max_bytes:
            raise ShareCountPublicationTooLarge("share-count external immutable artifact exceeds byte cap")
        prior = self._artifacts.get(key)
        if prior is not None and prior != body:
            raise ShareCountPublicationConflict("share-count immutable external artifact already differs")
        self._artifacts[key] = body
        if self.read_artifact(key=key, max_bytes=max_bytes) != body:
            raise ShareCountPublicationError("share-count external immutable artifact read-back mismatch")

    def read_artifact(self, *, key: str, max_bytes: int) -> bytes:
        _validate_external_artifact_key(key)
        try:
            body = self._artifacts[key]
        except KeyError as exc:
            raise ShareCountPublicationError("share-count external immutable artifact is missing") from exc
        if not 1 <= len(body) <= max_bytes:
            raise ShareCountPublicationTooLarge("share-count external immutable artifact exceeds byte cap")
        return body


class R2ShareCountHeadGuard:
    """R2-backed strict HEAD/GET/CAS witness and immutable recovery namespace."""

    def __init__(
        self,
        *,
        client: Any,
        bucket: str,
        signer: ShareCountSigner,
        account_id: str | None = None,
        key: str = HEAD_GUARD_KEY,
    ) -> None:
        if not bucket:
            raise ValueError("share-count head-guard bucket is required")
        if key != HEAD_GUARD_KEY:
            raise ValueError("share-count head-guard key must use the fixed publication selector")
        self._client, self._bucket, self._signer, self._key = client, bucket, signer, key
        self._guard_scope = (
            None
            if account_id is None
            else _head_guard_scope(account_id=account_id, bucket=bucket, head_key=key)
        )
        self._deadline_state: tuple[float, Callable[[], float]] | None = None

    @property
    def guard_scope(self) -> Mapping[str, Any]:
        if self._guard_scope is None:
            raise ShareCountPublicationError(
                "share-count v3 head guard requires SHARE_COUNT_HEAD_GUARD_ACCOUNT_ID",
            )
        return dict(self._guard_scope)

    @contextlib.contextmanager
    def _bind_deadline(self, operation: Any) -> Iterator[None]:
        previous = self._deadline_state
        self._deadline_state = (operation.deadline, operation.monotonic)
        try:
            yield
        finally:
            self._deadline_state = previous

    def _check_deadline(self, label: str) -> None:
        if self._deadline_state is None:
            return
        deadline, monotonic = self._deadline_state
        if monotonic() >= deadline:
            raise ShareCountPublicationError(
                f"share-count publication deadline exceeded during {label}",
            )

    def read(self) -> tuple[dict[str, Any] | None, str | None]:
        self._check_deadline("external head HEAD")
        try:
            head = self._client.head_object(Bucket=self._bucket, Key=self._key)
        except Exception as exc:  # noqa: BLE001
            if _is_not_found_error(exc):
                self._check_deadline("external head HEAD")
                return None, None
            raise ShareCountPublicationError("share-count external head witness is unreadable") from exc
        self._check_deadline("external head HEAD")
        body, etag = self._bounded_get_from_head(head, key=self._key, max_bytes=MAX_HEAD_WITNESS_BYTES)
        try:
            parsed = _parse_canonical_json(body, label="external head witness")
            _validate_any_head_witness(
                parsed,
                signer=self._signer,
                expected_scope=self._guard_scope,
            )
            return dict(parsed), etag
        except ShareCountPublicationError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ShareCountPublicationError("share-count external head witness is malformed") from exc

    def advance(
        self, *, expected: Mapping[str, Any] | None, expected_token: str | None,
        candidate: Mapping[str, Any],
    ) -> None:
        try:
            self._check_deadline("external head transition preflight")
            observed, token = self.read()
        except ShareCountPublicationError as exc:
            raise _ShareCountPreCasFailure(
                "share-count external head CAS was not invoked",
            ) from exc
        normalized = dict(expected) if expected is not None else None
        if observed is not None and observed.get("schema") == WITNESS_V3_SCHEMA:
            raise _ShareCountPreCasFailure(
                "share-count v3 external head is a migration fence; publication CAS was not invoked",
            )
        if observed != normalized or token != expected_token:
            raise ShareCountPublicationConflict("share-count external head compare-and-swap conflict")
        _validate_head_transition(previous=observed, candidate=candidate, signer=self._signer)
        body = _canonical_bytes(dict(candidate)) + b"\n"
        if len(body) > MAX_HEAD_WITNESS_BYTES:
            raise ShareCountPublicationTooLarge("share-count external head witness exceeds byte cap")
        arguments: dict[str, Any] = {"Bucket": self._bucket, "Key": self._key, "Body": body, "ContentType": "application/json"}
        arguments["IfNoneMatch" if token is None else "IfMatch"] = "*" if token is None else token
        try:
            self._check_deadline("external head conditional PUT")
        except ShareCountPublicationError as exc:
            raise _ShareCountPreCasFailure(
                "share-count external head CAS was not invoked",
            ) from exc
        try:
            self._client.put_object(**arguments)
            self._check_deadline("external head conditional PUT")
        except Exception as exc:  # noqa: BLE001
            if _is_conditional_write_conflict(exc):
                raise ShareCountPublicationConflict("share-count external head compare-and-swap conflict") from exc
            # A transport failure after the server received the request is not a
            # normal pre-CAS error.  Resolve only an exact read-back; otherwise
            # retain the local signed recovery state for restart reconciliation.
            try:
                confirmed, _ = self.read()
            except Exception as read_exc:  # noqa: BLE001
                raise ShareCountPublishIndeterminate("share-count external head CAS outcome is indeterminate") from read_exc
            if confirmed != dict(candidate):
                raise ShareCountPublishIndeterminate("share-count external head CAS outcome is indeterminate") from exc
            return
        confirmed, _ = self.read()
        if confirmed != dict(candidate):
            raise ShareCountPublicationError("share-count external head read-back mismatch")

    def migrate_v2_to_v3(
        self,
        *,
        expected: Mapping[str, Any],
        expected_token: str,
        candidate: Mapping[str, Any],
    ) -> None:
        scope = self.guard_scope
        try:
            self._check_deadline("external head v3 migration preflight")
            observed, token = self.read()
        except ShareCountPublicationError as exc:
            raise _ShareCountPreCasFailure(
                "share-count external head v3 migration CAS was not invoked",
            ) from exc
        if observed != dict(expected) or token != expected_token:
            raise ShareCountPublicationConflict(
                "share-count external head v3 migration compare-and-swap conflict",
            )
        _validate_head_migration(
            previous=expected,
            candidate=candidate,
            signer=self._signer,
            expected_scope=scope,
        )
        body = _canonical_bytes(dict(candidate)) + b"\n"
        if len(body) > MAX_HEAD_WITNESS_BYTES:
            raise ShareCountPublicationTooLarge(
                "share-count external head v3 witness exceeds byte cap",
            )
        arguments = {
            "Bucket": self._bucket,
            "Key": self._key,
            "Body": body,
            "ContentType": "application/json",
            "IfMatch": expected_token,
        }
        try:
            self._check_deadline("external head v3 migration conditional PUT")
        except ShareCountPublicationError as exc:
            raise _ShareCountPreCasFailure(
                "share-count external head v3 migration CAS was not invoked",
            ) from exc
        try:
            self._client.put_object(**arguments)
            self._check_deadline("external head v3 migration conditional PUT")
        except Exception as exc:  # noqa: BLE001
            if _is_conditional_write_conflict(exc):
                raise ShareCountPublicationConflict(
                    "share-count external head v3 migration compare-and-swap conflict",
                ) from exc
            try:
                confirmed, _ = self.read()
            except Exception as read_exc:  # noqa: BLE001
                raise ShareCountPublishIndeterminate(
                    "share-count external head v3 migration outcome is indeterminate",
                ) from read_exc
            if confirmed != dict(candidate):
                raise ShareCountPublishIndeterminate(
                    "share-count external head v3 migration outcome is indeterminate",
                ) from exc
            return
        confirmed, _ = self.read()
        if confirmed != dict(candidate):
            raise ShareCountPublicationError(
                "share-count external head v3 migration read-back mismatch",
            )

    def seal_artifact(self, *, key: str, body: bytes, max_bytes: int) -> None:
        _validate_external_artifact_key(key)
        if not isinstance(body, bytes) or not 1 <= len(body) <= max_bytes:
            raise ShareCountPublicationTooLarge("share-count external immutable artifact exceeds byte cap")
        try:
            self._check_deadline("external immutable artifact PUT")
            self._client.put_object(
                Bucket=self._bucket, Key=key, Body=body, ContentType="application/json",
                IfNoneMatch="*",
            )
            self._check_deadline("external immutable artifact PUT")
        except Exception as exc:  # noqa: BLE001
            if not _is_conditional_write_conflict(exc):
                raise ShareCountPublicationError("share-count external immutable artifact write failed") from exc
        if self.read_artifact(key=key, max_bytes=max_bytes) != body:
            raise ShareCountPublicationConflict("share-count external immutable artifact already differs")

    def read_artifact(self, *, key: str, max_bytes: int) -> bytes:
        _validate_external_artifact_key(key)
        try:
            self._check_deadline("external immutable artifact HEAD")
            head = self._client.head_object(Bucket=self._bucket, Key=key)
            self._check_deadline("external immutable artifact HEAD")
        except Exception as exc:  # noqa: BLE001
            raise ShareCountPublicationError("share-count external immutable artifact is unreadable") from exc
        body, _ = self._bounded_get_from_head(head, key=key, max_bytes=max_bytes)
        return body

    def _bounded_get_from_head(self, head: Any, *, key: str, max_bytes: int) -> tuple[bytes, str]:
        self._check_deadline("external bounded object validation")
        if not isinstance(head, Mapping):
            raise ShareCountPublicationError("share-count external object HEAD is malformed")
        length, etag = head.get("ContentLength"), head.get("ETag")
        if isinstance(length, bool) or not isinstance(length, int) or not 1 <= length <= max_bytes:
            raise ShareCountPublicationTooLarge("share-count external object HEAD length exceeds byte cap")
        if not isinstance(etag, str) or not etag.strip():
            raise ShareCountPublicationError("share-count external object HEAD has no CAS token")
        try:
            self._check_deadline("external bounded object GET")
            response = self._client.get_object(
                Bucket=self._bucket, Key=key, Range=f"bytes=0-{length - 1}", IfMatch=etag,
            )
            self._check_deadline("external bounded object GET")
        except Exception as exc:  # noqa: BLE001
            raise ShareCountPublicationError("share-count external object is unreadable") from exc
        if not isinstance(response, Mapping) or response.get("ContentLength") != length or response.get("ETag") != etag:
            raise ShareCountPublicationError("share-count external object GET/HEAD mismatch")
        stream = response.get("Body")
        if not callable(getattr(stream, "read", None)) or not callable(getattr(stream, "close", None)):
            raise ShareCountPublicationError("share-count external object body is unreadable")
        try:
            chunks: list[bytes] = []
            observed = 0
            while observed < length + 1:
                self._check_deadline("external bounded object stream")
                wanted = min(64 * 1024, length + 1 - observed)
                chunk = stream.read(wanted)
                self._check_deadline("external bounded object stream")
                if not isinstance(chunk, bytes) or len(chunk) > wanted:
                    raise ShareCountPublicationError("share-count external object body violated read bounds")
                if not chunk:
                    break
                chunks.append(chunk); observed += len(chunk)
            body = b"".join(chunks)
            if len(body) != length:
                raise ShareCountPublicationError("share-count external object body length mismatch")
            return body, etag
        finally:
            try:
                stream.close()
            except Exception as exc:  # noqa: BLE001
                raise ShareCountPublicationError("share-count external object body close failed") from exc
            self._check_deadline("external bounded object close")


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ShareCountPublicationError("share-count publication value is not canonical JSON data") from exc


def _validate_contract(record: Mapping[str, Any], filename: str, *, label: str) -> None:
    """Run the tracked contract as well as narrow semantic checks below."""
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        schema_path = Path(__file__).resolve().parents[2] / "contracts" / filename
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(dict(record)))
    except ShareCountPublicationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ShareCountPublicationError(f"share-count {label} contract is unavailable") from exc
    if errors:
        detail = "; ".join(
            f"{'.'.join(str(piece) for piece in err.absolute_path) or '<root>'}: {err.message}"
            for err in errors[:4]
        )
        raise ShareCountPublicationError(f"share-count {label} contract violation: {detail}")


def _parse_canonical_json(body: bytes, *, label: str, max_bytes: int | None = None) -> dict[str, Any]:
    if not isinstance(body, bytes) or not body:
        raise ShareCountPublicationError(f"share-count {label} bytes are invalid")
    if max_bytes is not None and len(body) > max_bytes:
        raise ShareCountPublicationTooLarge(f"share-count {label} exceeds byte cap")
    try:
        parsed = json.loads(body)
    except Exception as exc:  # noqa: BLE001
        raise ShareCountPublicationError(f"share-count {label} is unreadable") from exc
    if not isinstance(parsed, Mapping) or body != _canonical_bytes(parsed) + b"\n":
        raise ShareCountPublicationError(f"share-count {label} is not canonical")
    return dict(parsed)


def _sha(body: bytes) -> str:
    return sha256(body).hexdigest()


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and bool(_HEX64.fullmatch(value))


def _head_guard_scope(
    *,
    account_id: str,
    bucket: str,
    head_key: str,
) -> dict[str, str]:
    record = {
        "schema": HEAD_GUARD_SCOPE_SCHEMA,
        "backend": "r2",
        "account_id": account_id,
        "bucket": bucket,
        "head_key": head_key,
    }
    return _validate_head_guard_scope(record)


def _validate_head_guard_scope(
    record: Mapping[str, Any],
    *,
    expected: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    required = {"schema", "backend", "account_id", "bucket", "head_key"}
    if (
        not isinstance(record, Mapping)
        or set(record) != required
        or record.get("schema") != HEAD_GUARD_SCOPE_SCHEMA
        or record.get("backend") != "r2"
        or not isinstance(record.get("account_id"), str)
        or not _HEX32.fullmatch(record["account_id"])
        or not isinstance(record.get("bucket"), str)
        or not record["bucket"]
        or record.get("head_key") != HEAD_GUARD_KEY
    ):
        raise ShareCountPublicationError("share-count v3 head guard scope is invalid")
    _validate_contract(
        record,
        "capital_structure_share_count_head_guard_scope.schema.json",
        label="v3 head guard scope",
    )
    normalized = dict(record)
    if expected is not None and normalized != dict(expected):
        raise ShareCountPublicationError(
            "share-count v3 head guard scope does not match the configured R2 authority",
        )
    return normalized  # type: ignore[return-value]


def _id_digest(value: object, *, prefix: str, label: str) -> str:
    if not isinstance(value, str) or not value.startswith(prefix) or not _is_hex64(value[len(prefix):]):
        raise ShareCountPublicationError(f"share-count {label} identity is invalid")
    return value[len(prefix):]


def _iso(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ShareCountPublicationError("share-count publication timestamp must be timezone-aware")
    stamp = value.astimezone(timezone.utc)
    return stamp.isoformat(timespec="microseconds" if stamp.microsecond else "seconds").replace("+00:00", "Z")


def _stamp(value: object, *, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ShareCountPublicationError(f"share-count {label} is invalid")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ShareCountPublicationError(f"share-count {label} is invalid") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ShareCountPublicationError(f"share-count {label} lacks timezone")
    return result.astimezone(timezone.utc)


def _output_authority() -> dict[str, bool]:
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
        "trade_authority": False,
        "prophet_authority": False,
    }


def _receipt_auth_payload(record: Mapping[str, Any]) -> bytes:
    material = dict(record)
    auth = material.get("auth")
    if not isinstance(auth, Mapping):
        raise ShareCountPublicationError("share-count receipt authentication envelope is missing")
    material["auth"] = {key: value for key, value in auth.items() if key != "signature"}
    return _canonical_bytes({"domain": RECEIPT_SCHEMA, "receipt": material})


def _receipt_identity_material(record: Mapping[str, Any]) -> dict[str, Any]:
    material = dict(record)
    material.pop("receipt_id", None)
    auth = material.get("auth")
    if isinstance(auth, Mapping):
        material["auth"] = {key: value for key, value in auth.items() if key != "signature"}
    return material


def _receipt_id(record: Mapping[str, Any]) -> str:
    return _RECEIPT_PREFIX + _sha(_canonical_bytes(_receipt_identity_material(record)))


def _generation_id(ledger_sha256: str) -> str:
    if not _is_hex64(ledger_sha256):
        raise ShareCountPublicationError("share-count generation digest is invalid")
    return _GENERATION_PREFIX + ledger_sha256


def _receipt_external_key(receipt_id: str) -> str:
    return "capital_structure/share_counts/v2/receipts/" + _id_digest(
        receipt_id, prefix=_RECEIPT_PREFIX, label="receipt",
    ) + ".json"


def _ledger_external_key(generation_id: str) -> str:
    return "capital_structure/share_counts/v2/generations/" + _id_digest(
        generation_id, prefix=_GENERATION_PREFIX, label="generation",
    ) + "/ledger.json"


def _ledger_local_relative(generation_id: str) -> str:
    return "data/capital_structure/share_counts/v2/generations/" + _id_digest(
        generation_id, prefix=_GENERATION_PREFIX, label="generation",
    ) + "/ledger.json"


def _receipt_local_relative(receipt_id: str) -> str:
    return "data/capital_structure/share_counts/v2/receipts/" + _id_digest(
        receipt_id, prefix=_RECEIPT_PREFIX, label="receipt",
    ) + ".json"


def _pointer_id(record: Mapping[str, Any]) -> str:
    material = dict(record); material.pop("pointer_id", None)
    return _POINTER_PREFIX + _sha(_canonical_bytes(material))


def _head_payload(record: Mapping[str, Any]) -> bytes:
    material = dict(record); material.pop("signature", None)
    return _canonical_bytes({"domain": WITNESS_V2_SCHEMA, "witness": material})


def _head_v3_payload(record: Mapping[str, Any]) -> bytes:
    material = dict(record); material.pop("signature", None)
    return _canonical_bytes({"domain": WITNESS_V3_SCHEMA, "witness": material})


def _pending_payload(record: Mapping[str, Any]) -> bytes:
    material = dict(record); material.pop("signature", None)
    return _canonical_bytes({"domain": PENDING_SCHEMA, "pending": material})


def _recovery_payload(record: Mapping[str, Any]) -> bytes:
    material = dict(record); material.pop("signature", None)
    return _canonical_bytes({"domain": RECOVERY_SCHEMA, "recovery": material})


def _journal_payload(record: Mapping[str, Any]) -> bytes:
    material = dict(record); material.pop("signature", None)
    return _canonical_bytes({"domain": JOURNAL_SCHEMA, "journal": material})


def _validate_external_artifact_key(key: object) -> None:
    if not isinstance(key, str) or not (
        re.fullmatch(r"capital_structure/share_counts/v2/receipts/[a-f0-9]{64}\.json", key)
        or re.fullmatch(r"capital_structure/share_counts/v2/generations/[a-f0-9]{64}/ledger\.json", key)
    ):
        raise ShareCountPublicationError("share-count external artifact key is unsafe")


def _validate_binding_shape(binding: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(binding, Mapping) or set(binding) != _INPUT_BINDING_FIELDS:
        raise ShareCountPublicationError("share-count input binding shape is invalid")
    normalized = json.loads(_canonical_bytes(dict(binding)))
    if normalized.get("schema") != "capital_structure.share_count_materialization_input_binding/v1":
        raise ShareCountPublicationError("share-count input binding schema is invalid")
    if not isinstance(normalized.get("ledger_head_receipt_id"), str) or re.fullmatch(
        r"share-count-ledger-receipt-v2:cs:[a-f0-9]{24}",
        normalized["ledger_head_receipt_id"],
    ) is None:
        raise ShareCountPublicationError("share-count input binding ledger head is invalid")
    sequence = normalized.get("ledger_sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or not 1 <= sequence <= 4096:
        raise ShareCountPublicationError("share-count input binding sequence is invalid")
    compiler_version = normalized.get("compiler_version")
    if not isinstance(compiler_version, str) or not compiler_version:
        raise ShareCountPublicationError("share-count input binding compiler version is invalid")
    _stamp(normalized.get("materialized_at"), label="input binding materialized_at")
    prefixes = normalized.get("prefixes")
    if not isinstance(prefixes, Mapping) or set(prefixes) != _PREFIX_LABELS:
        raise ShareCountPublicationError("share-count input binding prefixes are invalid")
    for label in sorted(_PREFIX_LABELS):
        prefix = prefixes.get(label)
        if not isinstance(prefix, Mapping) or set(prefix) != {"count", "rolling_sha256"}:
            raise ShareCountPublicationError("share-count input binding prefixes are invalid")
        count = prefix.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= MAX_PREFIX_COUNT:
            raise ShareCountPublicationError("share-count input binding prefix count is invalid")
        if not _is_hex64(prefix.get("rolling_sha256")):
            raise ShareCountPublicationError("share-count input binding prefix digest is invalid")
    source_counts = {
        int(prefixes[label]["count"])
        for label in ("source_snapshots", "bridges", "source_manifests")
    }
    if source_counts == {0} or len(source_counts) != 1:
        raise ShareCountPublicationError(
            "share-count input binding source prefix counts are inconsistent",
        )
    return normalized


def _validate_input_binding(binding: Mapping[str, Any], ledger: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _validate_binding_shape(binding)
    receipts = ledger.get("ledger_receipts")
    if not isinstance(receipts, list) or not receipts:
        raise ShareCountPublicationError("share-count ledger has no materializer receipt tail")
    tail = receipts[-1]
    if not isinstance(tail, Mapping):
        raise ShareCountPublicationError("share-count materializer receipt tail is invalid")
    expected = {
        "schema": "capital_structure.share_count_materialization_input_binding/v1",
        "ledger_head_receipt_id": ledger.get("ledger_head_receipt_id"),
        "ledger_sequence": tail.get("sequence"),
        "compiler_version": ledger.get("compiler_version"),
        "materialized_at": ledger.get("materialized_at"),
        "prefixes": tail.get("prefixes"),
    }
    if normalized != expected:
        raise ShareCountPublicationError(
            "share-count input binding is detached from exact ledger tail prefixes",
        )
    return normalized


def _validate_receipt_ref(
    record: Mapping[str, Any], *, label: str, expected_sequence: int | None = None,
) -> dict[str, Any]:
    required = {"sequence", "receipt_id", "receipt_sha256", "receipt_byte_length"}
    if not isinstance(record, Mapping) or set(record) != required:
        raise ShareCountPublicationError(f"share-count {label} reference is invalid")
    sequence = record.get("sequence")
    if (
        isinstance(sequence, bool)
        or not isinstance(sequence, int)
        or not 1 <= sequence <= MAX_RECEIPT_SEQUENCE
        or (expected_sequence is not None and sequence != expected_sequence)
    ):
        raise ShareCountPublicationError(f"share-count {label} reference sequence is invalid")
    _id_digest(record.get("receipt_id"), prefix=_RECEIPT_PREFIX, label=label)
    if (
        not _is_hex64(record.get("receipt_sha256"))
        or isinstance(record.get("receipt_byte_length"), bool)
        or not isinstance(record.get("receipt_byte_length"), int)
        or not 1 <= record["receipt_byte_length"] <= MAX_RECEIPT_BYTES
    ):
        raise ShareCountPublicationError(f"share-count {label} reference is invalid")
    return dict(record)


def _receipt_ref(receipt: Mapping[str, Any], receipt_body: bytes) -> dict[str, Any]:
    return {
        "sequence": receipt["sequence"],
        "receipt_id": receipt["receipt_id"],
        "receipt_sha256": _sha(receipt_body),
        "receipt_byte_length": len(receipt_body),
    }


def _head_receipt_ref(head: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "sequence": head["sequence"],
        "receipt_id": head["receipt_id"],
        "receipt_sha256": head["receipt_sha256"],
        "receipt_byte_length": head["receipt_byte_length"],
    }


def _validate_receipt(record: Mapping[str, Any], *, signer: ShareCountSigner) -> dict[str, Any]:
    required = {
        "schema", "receipt_id", "sequence", "previous_receipt", "published_at", "generation",
        "ancestor_refs", "input_binding", "output_authority", "auth",
    }
    if not isinstance(record, Mapping) or set(record) != required or record.get("schema") != RECEIPT_SCHEMA:
        raise ShareCountPublicationError("share-count materialization receipt shape is invalid")
    _validate_contract(record, "capital_structure_share_count_materialization_receipt.schema.json", label="materialization receipt")
    if (
        not isinstance(record.get("sequence"), int)
        or isinstance(record["sequence"], bool)
        or not 1 <= record["sequence"] <= MAX_RECEIPT_SEQUENCE
    ):
        raise ShareCountPublicationError("share-count materialization receipt sequence is invalid")
    _stamp(record.get("published_at"), label="receipt timestamp")
    if record.get("receipt_id") != _receipt_id(record):
        raise ShareCountPublicationError("share-count materialization receipt identity mismatch")
    generation = record.get("generation")
    if not isinstance(generation, Mapping) or set(generation) != {"generation_id", "ledger_sha256", "ledger_byte_length"}:
        raise ShareCountPublicationError("share-count materialization generation shape is invalid")
    digest = generation.get("ledger_sha256")
    if not _is_hex64(digest) or generation.get("generation_id") != _generation_id(digest):
        raise ShareCountPublicationError("share-count materialization generation identity is invalid")
    length = generation.get("ledger_byte_length")
    if not isinstance(length, int) or isinstance(length, bool) or not 1 <= length <= MAX_LEDGER_BYTES:
        raise ShareCountPublicationTooLarge("share-count materialization ledger length is invalid")
    previous = record.get("previous_receipt")
    ancestors = record.get("ancestor_refs")
    expected_ancestor_count = (record["sequence"] - 1).bit_length()
    if (
        not isinstance(ancestors, list)
        or len(ancestors) != expected_ancestor_count
        or len(ancestors) > MAX_ANCESTOR_REFS
    ):
        raise ShareCountPublicationError("share-count binary-lifting ancestor table is invalid")
    if record["sequence"] == 1:
        if previous is not None or ancestors:
            raise ShareCountPublicationError("share-count genesis receipt has a predecessor")
    else:
        previous = _validate_receipt_ref(
            previous,
            label="predecessor receipt",
            expected_sequence=record["sequence"] - 1,
        )
        for level, ancestor in enumerate(ancestors):
            expected_sequence = record["sequence"] - (1 << level)
            normalized = _validate_receipt_ref(
                ancestor,
                label=f"ancestor level {level}",
                expected_sequence=expected_sequence,
            )
            if normalized != ancestor:
                raise ShareCountPublicationError(
                    "share-count binary-lifting ancestor reference is noncanonical",
                )
        if ancestors[0] != previous:
            raise ShareCountPublicationError(
                "share-count binary-lifting predecessor reference is detached",
            )
    # Receipt-level validation pins the closed constant-size tail commitments;
    # only the production entry can additionally rederive them from the ledger.
    _validate_binding_shape(record.get("input_binding"))
    if record.get("output_authority") != _output_authority():
        raise ShareCountPublicationError("share-count materialization output authority must be all-false")
    auth = record.get("auth")
    if not isinstance(auth, Mapping) or set(auth) != {"scheme", "key_id", "signature"} or auth.get("scheme") != AUTH_SCHEME or not isinstance(auth.get("key_id"), str) or not signer.verify(_receipt_auth_payload(record), auth.get("signature"), key_id=auth["key_id"]):
        raise ShareCountPublicationError("share-count materialization receipt authentication mismatch")
    return dict(record)


def _head_witness(*, receipt: Mapping[str, Any], receipt_body: bytes, signer: ShareCountSigner) -> dict[str, Any]:
    previous = receipt["previous_receipt"]
    record: dict[str, Any] = {
        "schema": WITNESS_SCHEMA,
        "key_id": signer.key_id,
        "sequence": receipt["sequence"],
        "receipt_id": receipt["receipt_id"],
        "receipt_sha256": _sha(receipt_body),
        "receipt_byte_length": len(receipt_body),
        "receipt_object_key": _receipt_external_key(receipt["receipt_id"]),
        "generation_id": receipt["generation"]["generation_id"],
        "ledger_sha256": receipt["generation"]["ledger_sha256"],
        "ledger_byte_length": receipt["generation"]["ledger_byte_length"],
        "ledger_object_key": _ledger_external_key(receipt["generation"]["generation_id"]),
        "published_at": receipt["published_at"],
        "previous_receipt": dict(previous) if isinstance(previous, Mapping) else None,
    }
    record["signature"] = signer.sign(_head_payload(record))
    _validate_head_witness(record, signer=signer)
    return record


def _validate_head_witness(record: Mapping[str, Any], *, signer: ShareCountSigner) -> dict[str, Any]:
    required = {"schema", "key_id", "signature"} | _HEAD_SELECTION_FIELDS
    if not isinstance(record, Mapping) or set(record) != required or record.get("schema") != WITNESS_V2_SCHEMA:
        raise ShareCountPublicationError("share-count external head witness shape is invalid")
    _validate_contract(
        record,
        "capital_structure_share_count_head_witness.schema.json",
        label="share-count head witness",
    )
    _validate_head_selection(record)
    if not isinstance(record.get("key_id"), str) or not signer.verify(_head_payload(record), record.get("signature"), key_id=record["key_id"]):
        raise ShareCountPublicationError("share-count external head witness authentication mismatch")
    return dict(record)


def _validate_head_selection(record: Mapping[str, Any]) -> None:
    if (
        not isinstance(record.get("sequence"), int)
        or isinstance(record["sequence"], bool)
        or not 1 <= record["sequence"] <= MAX_RECEIPT_SEQUENCE
    ):
        raise ShareCountPublicationError("share-count external head witness sequence is invalid")
    _id_digest(record.get("receipt_id"), prefix=_RECEIPT_PREFIX, label="head receipt")
    _id_digest(record.get("generation_id"), prefix=_GENERATION_PREFIX, label="head generation")
    if not _is_hex64(record.get("receipt_sha256")) or not _is_hex64(record.get("ledger_sha256")):
        raise ShareCountPublicationError("share-count external head witness digest is invalid")
    for field, cap in (("receipt_byte_length", MAX_RECEIPT_BYTES), ("ledger_byte_length", MAX_LEDGER_BYTES)):
        value = record.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= cap:
            raise ShareCountPublicationTooLarge("share-count external head witness length is invalid")
    if record.get("receipt_object_key") != _receipt_external_key(record["receipt_id"]) or record.get("ledger_object_key") != _ledger_external_key(record["generation_id"]):
        raise ShareCountPublicationError("share-count external head witness artifact key is invalid")
    if record.get("generation_id") != _generation_id(record["ledger_sha256"]):
        raise ShareCountPublicationError("share-count external head witness generation is detached")
    _stamp(record.get("published_at"), label="head witness timestamp")
    predecessor = record.get("previous_receipt")
    if record["sequence"] == 1:
        if predecessor is not None:
            raise ShareCountPublicationError("share-count external head genesis predecessor is invalid")
    else:
        _validate_receipt_ref(
            predecessor,
            label="head predecessor",
            expected_sequence=record["sequence"] - 1,
        )


def _validate_head_witness_v3(
    record: Mapping[str, Any],
    *,
    signer: ShareCountSigner,
    expected_scope: Mapping[str, Any] | None,
) -> dict[str, Any]:
    required = {
        "schema", "key_id", "guard_scope", "migration", "signature",
    } | _HEAD_SELECTION_FIELDS
    if (
        not isinstance(record, Mapping)
        or set(record) != required
        or record.get("schema") != WITNESS_V3_SCHEMA
    ):
        raise ShareCountPublicationError("share-count v3 external head witness shape is invalid")
    _validate_contract(
        record,
        "capital_structure_share_count_head_witness_v3.schema.json",
        label="share-count v3 head witness",
    )
    _validate_head_selection(record)
    scope = record.get("guard_scope")
    if not isinstance(scope, Mapping):
        raise ShareCountPublicationError("share-count v3 head guard scope is invalid")
    _validate_head_guard_scope(scope, expected=expected_scope)
    migration = record.get("migration")
    if (
        not isinstance(migration, Mapping)
        or set(migration) != {"from_schema", "from_witness_sha256"}
        or migration.get("from_schema") != WITNESS_V2_SCHEMA
        or not _is_hex64(migration.get("from_witness_sha256"))
    ):
        raise ShareCountPublicationError("share-count v3 head migration binding is invalid")
    verify = getattr(signer, "verify_head_v3", None)
    if (
        not isinstance(record.get("key_id"), str)
        or not callable(verify)
        or not verify(
            _head_v3_payload(record),
            record.get("signature"),
            key_id=record["key_id"],
        )
    ):
        raise ShareCountPublicationError(
            "share-count v3 external head witness authentication mismatch",
        )
    return dict(record)


def _validate_any_head_witness(
    record: Mapping[str, Any],
    *,
    signer: ShareCountSigner,
    expected_scope: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise ShareCountPublicationError("share-count external head witness shape is invalid")
    if record.get("schema") == WITNESS_V2_SCHEMA:
        return _validate_head_witness(record, signer=signer)
    if record.get("schema") == WITNESS_V3_SCHEMA:
        if expected_scope is None:
            raise ShareCountPublicationError(
                "share-count v3 head guard requires an explicit configured scope",
            )
        return _validate_head_witness_v3(
            record,
            signer=signer,
            expected_scope=expected_scope,
        )
    raise ShareCountPublicationError("share-count external head witness schema is unsupported")


def _head_selection(record: Mapping[str, Any]) -> dict[str, Any]:
    return {field: record[field] for field in sorted(_HEAD_SELECTION_FIELDS)}


def _migrated_head_witness_v3(
    previous: Mapping[str, Any],
    *,
    signer: ShareCountSigner,
    guard_scope: Mapping[str, Any],
) -> dict[str, Any]:
    previous = _validate_head_witness(previous, signer=signer)
    scope = _validate_head_guard_scope(guard_scope)
    previous_body = _canonical_bytes(previous) + b"\n"
    candidate: dict[str, Any] = {
        "schema": WITNESS_V3_SCHEMA,
        "key_id": signer.key_id,
        **_head_selection(previous),
        "guard_scope": scope,
        "migration": {
            "from_schema": WITNESS_V2_SCHEMA,
            "from_witness_sha256": _sha(previous_body),
        },
        "signature": "",
    }
    sign = getattr(signer, "sign_head_v3", None)
    if not callable(sign):
        raise ShareCountPublicationError("share-count v3 head signer is unavailable")
    candidate["signature"] = sign(_head_v3_payload(candidate))
    return _validate_head_witness_v3(
        candidate,
        signer=signer,
        expected_scope=scope,
    )


def _validate_head_migration(
    *,
    previous: Mapping[str, Any],
    candidate: Mapping[str, Any],
    signer: ShareCountSigner,
    expected_scope: Mapping[str, Any],
) -> None:
    previous = _validate_head_witness(previous, signer=signer)
    candidate = _validate_head_witness_v3(
        candidate,
        signer=signer,
        expected_scope=expected_scope,
    )
    if _head_selection(candidate) != _head_selection(previous):
        raise ShareCountPublicationError(
            "share-count v3 head migration changed the selected generation",
        )
    expected_migration = {
        "from_schema": WITNESS_V2_SCHEMA,
        "from_witness_sha256": _sha(_canonical_bytes(previous) + b"\n"),
    }
    if candidate["migration"] != expected_migration:
        raise ShareCountPublicationError(
            "share-count v3 head migration is detached from exact v2 witness bytes",
        )


def _virtual_v2_witness_from_v3(
    record: Mapping[str, Any],
    *,
    signer: ShareCountSigner,
    expected_scope: Mapping[str, Any],
) -> dict[str, Any]:
    """Reconstruct and authenticate the sole v2 witness a v3 fence may wrap.

    A v3 witness is migration-only.  Recovery protocols whose durable intent
    predates that fence may reason about it only after proving that its signed
    migration digest names the deterministic same-selection v2 bytes.
    """
    migrated = _validate_head_witness_v3(
        record,
        signer=signer,
        expected_scope=expected_scope,
    )
    virtual: dict[str, Any] = {
        "schema": WITNESS_V2_SCHEMA,
        "key_id": migrated["key_id"],
        **_head_selection(migrated),
        "signature": "",
    }
    virtual["signature"] = signer.sign(_head_payload(virtual))
    virtual = _validate_head_witness(virtual, signer=signer)
    if migrated["migration"] != {
        "from_schema": WITNESS_V2_SCHEMA,
        "from_witness_sha256": _sha(_canonical_bytes(virtual) + b"\n"),
    }:
        raise ShareCountPublicationError(
            "share-count v3 head migration is detached from its virtual v2 witness",
        )
    return virtual


def _validate_head_transition(*, previous: Mapping[str, Any] | None, candidate: Mapping[str, Any], signer: ShareCountSigner) -> None:
    candidate = _validate_head_witness(candidate, signer=signer)
    if previous is None:
        if candidate["sequence"] != 1 or candidate["previous_receipt"] is not None:
            raise ShareCountPublicationError("share-count external head genesis transition is invalid")
        return
    previous = _validate_head_witness(previous, signer=signer)
    if (
        candidate["sequence"] != previous["sequence"] + 1
        or candidate["previous_receipt"] != _head_receipt_ref(previous)
    ):
        raise ShareCountPublicationError("share-count external head transition is not exact-predecessor")


def _pointer_for(*, receipt: Mapping[str, Any], receipt_body: bytes) -> dict[str, Any]:
    generation = receipt["generation"]
    pointer: dict[str, Any] = {
        "schema": POINTER_SCHEMA,
        "sequence": receipt["sequence"],
        "receipt_id": receipt["receipt_id"],
        "receipt_path": _receipt_local_relative(receipt["receipt_id"]),
        "receipt_sha256": _sha(receipt_body),
        "receipt_byte_length": len(receipt_body),
        "generation_id": generation["generation_id"],
        "ledger_path": _ledger_local_relative(generation["generation_id"]),
        "ledger_sha256": generation["ledger_sha256"],
        "ledger_byte_length": generation["ledger_byte_length"],
        "published_at": receipt["published_at"],
    }
    pointer["pointer_id"] = _pointer_id(pointer)
    _validate_pointer(pointer)
    return pointer


def _validate_pointer(record: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "schema", "pointer_id", "sequence", "receipt_id", "receipt_path", "receipt_sha256", "receipt_byte_length",
        "generation_id", "ledger_path", "ledger_sha256", "ledger_byte_length", "published_at",
    }
    if not isinstance(record, Mapping) or set(record) != required or record.get("schema") != POINTER_SCHEMA:
        raise ShareCountPublicationError("share-count current pointer shape is invalid")
    _validate_contract(record, "capital_structure_share_count_current_pointer.schema.json", label="current pointer")
    if record.get("pointer_id") != _pointer_id(record):
        raise ShareCountPublicationError("share-count current pointer identity mismatch")
    if (
        not isinstance(record.get("sequence"), int)
        or isinstance(record["sequence"], bool)
        or not 1 <= record["sequence"] <= MAX_RECEIPT_SEQUENCE
    ):
        raise ShareCountPublicationError("share-count current pointer sequence is invalid")
    _id_digest(record.get("receipt_id"), prefix=_RECEIPT_PREFIX, label="pointer receipt")
    _id_digest(record.get("generation_id"), prefix=_GENERATION_PREFIX, label="pointer generation")
    if record.get("receipt_path") != _receipt_local_relative(record["receipt_id"]) or record.get("ledger_path") != _ledger_local_relative(record["generation_id"]):
        raise ShareCountPublicationError("share-count current pointer artifact path is invalid")
    if record.get("generation_id") != _generation_id(record.get("ledger_sha256")) or not _is_hex64(record.get("receipt_sha256")):
        raise ShareCountPublicationError("share-count current pointer digest is invalid")
    for field, cap in (("receipt_byte_length", MAX_RECEIPT_BYTES), ("ledger_byte_length", MAX_LEDGER_BYTES)):
        value = record.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= cap:
            raise ShareCountPublicationTooLarge("share-count current pointer length is invalid")
    _stamp(record.get("published_at"), label="current pointer timestamp")
    return dict(record)


def _pointer_matches_witness(pointer: Mapping[str, Any], witness: Mapping[str, Any]) -> bool:
    return all((
        pointer.get("sequence") == witness.get("sequence"),
        pointer.get("receipt_id") == witness.get("receipt_id"),
        pointer.get("receipt_sha256") == witness.get("receipt_sha256"),
        pointer.get("receipt_byte_length") == witness.get("receipt_byte_length"),
        pointer.get("generation_id") == witness.get("generation_id"),
        pointer.get("ledger_sha256") == witness.get("ledger_sha256"),
        pointer.get("ledger_byte_length") == witness.get("ledger_byte_length"),
        pointer.get("published_at") == witness.get("published_at"),
    ))


def _decode_embedded_pointer(
    encoded: object,
    *,
    label: str,
) -> tuple[bytes | None, dict[str, Any] | None]:
    """Decode a canonical pointer carried by a signed recovery record."""
    if encoded is None:
        return None, None
    if not isinstance(encoded, str):
        raise ShareCountPublicationError(
            f"share-count {label} pointer encoding is invalid",
        )
    try:
        body = base64.b64decode(encoded, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise ShareCountPublicationError(
            f"share-count {label} pointer encoding is invalid",
        ) from exc
    pointer = _validate_pointer(
        _parse_canonical_json(
            body,
            label=f"{label} pointer",
            max_bytes=MAX_POINTER_BYTES,
        ),
    )
    return body, pointer


def _validate_embedded_pointer_transition(
    *,
    expected: Mapping[str, Any] | None,
    candidate: Mapping[str, Any],
    expected_pointer_b64: object,
    candidate_pointer_b64: object,
    label: str,
) -> tuple[bytes | None, bytes]:
    """Prove a recovery record's serialized pointers bind its two witnesses."""
    expected_body, expected_pointer = _decode_embedded_pointer(
        expected_pointer_b64,
        label=f"{label} predecessor",
    )
    candidate_body, candidate_pointer = _decode_embedded_pointer(
        candidate_pointer_b64,
        label=f"{label} candidate",
    )
    if candidate_body is None or candidate_pointer is None or not _pointer_matches_witness(
        candidate_pointer,
        candidate,
    ):
        raise ShareCountPublicationError(
            f"share-count {label} candidate pointer is detached",
        )
    if expected is None:
        if expected_body is not None:
            raise ShareCountPublicationError(
                f"share-count {label} genesis pointer is detached",
            )
    elif (
        expected_body is None
        or expected_pointer is None
        or not _pointer_matches_witness(expected_pointer, expected)
    ):
        raise ShareCountPublicationError(
            f"share-count {label} predecessor pointer is detached",
        )
    return expected_body, candidate_body


def _marker(*, expected: Mapping[str, Any] | None, candidate: Mapping[str, Any], expected_pointer: bytes | None, candidate_pointer: bytes, capsule: Mapping[str, Any], signer: ShareCountSigner) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema": PENDING_SCHEMA, "key_id": signer.key_id,
        "phase": "prepared",
        "expected_witness": dict(expected) if expected is not None else None,
        "candidate_witness": dict(candidate),
        "expected_pointer_b64": base64.b64encode(expected_pointer).decode("ascii") if expected_pointer else None,
        "candidate_pointer_b64": base64.b64encode(candidate_pointer).decode("ascii"),
        "recovery_sha256": capsule["sha256"], "recovery_byte_length": capsule["byte_length"],
    }
    record["signature"] = signer.sign(_pending_payload(record))
    _validate_marker(record, signer=signer)
    return record


def _validate_marker(record: Mapping[str, Any], *, signer: ShareCountSigner) -> dict[str, Any]:
    required = {"schema", "key_id", "phase", "expected_witness", "candidate_witness", "expected_pointer_b64", "candidate_pointer_b64", "recovery_sha256", "recovery_byte_length", "signature"}
    if not isinstance(record, Mapping) or set(record) != required or record.get("schema") != PENDING_SCHEMA or not isinstance(record.get("key_id"), str) or not signer.verify(_pending_payload(record), record.get("signature"), key_id=record["key_id"]):
        raise ShareCountPublicationError("share-count pending marker authentication mismatch")
    if record.get("phase") not in {"prepared", "cas_started"}:
        raise ShareCountPublicationError("share-count pending marker phase is invalid")
    expected = record.get("expected_witness")
    candidate = record.get("candidate_witness")
    if expected is not None and not isinstance(expected, Mapping):
        raise ShareCountPublicationError("share-count pending predecessor witness is invalid")
    if not isinstance(candidate, Mapping):
        raise ShareCountPublicationError("share-count pending candidate witness is invalid")
    _validate_head_transition(previous=expected, candidate=candidate, signer=signer)
    _validate_embedded_pointer_transition(
        expected=expected,
        candidate=candidate,
        expected_pointer_b64=record.get("expected_pointer_b64"),
        candidate_pointer_b64=record.get("candidate_pointer_b64"),
        label="pending marker",
    )
    if not _is_hex64(record.get("recovery_sha256")) or not isinstance(record.get("recovery_byte_length"), int) or not 1 <= record["recovery_byte_length"] <= MAX_RECOVERY_CAPSULE_BYTES:
        raise ShareCountPublicationError("share-count pending recovery reference is invalid")
    return dict(record)


@dataclass(frozen=True)
class ShareCountPublicationResult:
    """A bounded, already verified selected materialization generation."""

    receipt: Mapping[str, Any]
    pointer: Mapping[str, Any]
    ledger_path: Path
    ledger_bytes: bytes
    published: bool
    recovered: bool

    @property
    def generation_id(self) -> str:
        return str(self.receipt["generation"]["generation_id"])

    @property
    def receipt_id(self) -> str:
        return str(self.receipt["receipt_id"])

    @property
    def sequence(self) -> int:
        return int(self.receipt["sequence"])


@dataclass(frozen=True)
class _LocalReceiptSelection:
    """Authenticated local pointer and signed receipt, without ledger bytes."""

    receipt: Mapping[str, Any]
    receipt_body: bytes
    pointer: Mapping[str, Any]

    @property
    def receipt_id(self) -> str:
        return str(self.receipt["receipt_id"])

    @property
    def sequence(self) -> int:
        return int(self.receipt["sequence"])


@dataclass
class _RecoveryTrace:
    """Entry-state facts that must survive legacy cleanup during one lease."""

    legacy_seen_at_entry: bool = False
    journal_seen_at_entry: bool = False
    recovery_seen_at_entry: bool = False
    selected_head: Mapping[str, Any] | None = None


def _storage_root() -> Path:
    """Production root is fixed to the repository data directory's parent."""
    from lib import config

    return config.data_dir().parent


def _local_base(root: Path) -> Path:
    return root / "data" / "capital_structure" / "share_counts" / "v2"


@dataclass(frozen=True)
class _OperationDeadline:
    deadline: float
    monotonic: Callable[[], float]

    def check(self, label: str) -> None:
        if self.monotonic() >= self.deadline:
            raise ShareCountPublicationError(
                f"share-count publication deadline exceeded during {label}",
            )

    def run(self, label: str, call: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
        self.check(label)
        result = call(*args, **kwargs)
        # SDK and ordinary POSIX calls are not hard-cancellable here.  The
        # post-call check is load-bearing: a slow success may never escape as a
        # successful publication/recovery after the end-to-end deadline.
        self.check(label)
        return result


def _file_identity(value: os.stat_result) -> tuple[int, int]:
    return value.st_dev, value.st_ino


def _entry_name(name: str, *, label: str) -> str:
    if (
        not isinstance(name, str)
        or not name
        or name in {".", ".."}
        or "/" in name
        or "\x00" in name
    ):
        raise ShareCountPublicationError(f"share-count {label} path component is unsafe")
    return name


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )


@dataclass(frozen=True)
class _DirectoryBinding:
    parent_fd: int
    name: str
    fd: int
    identity: tuple[int, int]
    label: str


@dataclass(frozen=True)
class _EntryBinding:
    parent_fd: int
    name: str
    fd: int
    identity: tuple[int, int]
    label: str


def _open_directory_component(
    parent_fd: int,
    name: str,
    *,
    create: bool,
    operation: _OperationDeadline,
    label: str,
) -> tuple[int, _DirectoryBinding]:
    name = _entry_name(name, label=label)
    flags = _directory_flags()
    operation.check(f"{label} directory open")
    created = False
    try:
        fd = os.open(name, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        if not create:
            raise ShareCountPublicationError(f"share-count {label} directory is missing") from None
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
            created = True
        except FileExistsError:
            # A racer created the entry.  The no-follow directory open below
            # decides whether it is the directory we are willing to hold.
            pass
        except OSError as exc:
            raise ShareCountPublicationError(
                f"share-count {label} directory cannot be created safely",
            ) from exc
        operation.check(f"{label} directory create")
        try:
            fd = os.open(name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise ShareCountPublicationError(
                f"share-count {label} directory cannot be opened safely",
            ) from exc
    except OSError as exc:
        raise ShareCountPublicationError(
            f"share-count {label} directory cannot be opened safely",
        ) from exc
    try:
        opened = os.fstat(fd)
        linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        operation.check(f"{label} directory identity")
        if (
            not stat.S_ISDIR(opened.st_mode)
            or not stat.S_ISDIR(linked.st_mode)
            or _file_identity(opened) != _file_identity(linked)
        ):
            raise ShareCountPublicationError(f"share-count {label} directory is unsafe")
        if created:
            os.fsync(parent_fd)
            operation.check(f"{label} parent directory fsync")
        binding = _DirectoryBinding(
            parent_fd=parent_fd,
            name=name,
            fd=fd,
            identity=_file_identity(opened),
            label=label,
        )
        return fd, binding
    except BaseException:
        os.close(fd)
        raise


class _PublicationLane:
    """Held no-follow directory chain for one complete publication lease."""

    def __init__(
        self,
        *,
        root_path: Path,
        operation: _OperationDeadline,
        anchor_fd: int,
        anchor_identity: tuple[int, int],
        fds: list[int],
        bindings: list[_DirectoryBinding],
        root_fd: int,
        data_fd: int,
        capital_structure_fd: int,
        base_fd: int,
        receipts_fd: int,
        generations_fd: int,
        staging_fd: int,
    ) -> None:
        self.root_path = root_path
        self.operation = operation
        self.anchor_fd = anchor_fd
        self.anchor_identity = anchor_identity
        self._fds = fds
        self._bindings = bindings
        self.root_fd = root_fd
        self.data_fd = data_fd
        self.capital_structure_fd = capital_structure_fd
        self.base_fd = base_fd
        self.receipts_fd = receipts_fd
        self.generations_fd = generations_fd
        self.staging_fd = staging_fd
        self._lock_binding: _EntryBinding | None = None
        self._terminal_cleanup_armed = False

    @classmethod
    def open(cls, root: Path, *, operation: _OperationDeadline) -> "_PublicationLane":
        try:
            root_path = Path(os.path.abspath(os.fspath(root)))
        except (TypeError, ValueError, OSError) as exc:
            raise ShareCountPublicationError("share-count publication root is invalid") from exc
        if not root_path.is_absolute():  # pragma: no cover - abspath is absolute
            raise ShareCountPublicationError("share-count publication root must be absolute")
        operation.check("publication root traversal")
        fds: list[int] = []
        bindings: list[_DirectoryBinding] = []
        try:
            anchor_fd = os.open(os.sep, _directory_flags())
            fds.append(anchor_fd)
            anchor_stat = os.fstat(anchor_fd)
            if not stat.S_ISDIR(anchor_stat.st_mode):  # pragma: no cover - POSIX root
                raise ShareCountPublicationError("share-count filesystem root is unsafe")
            operation.check("filesystem root open")
            parent_fd = anchor_fd
            for index, component in enumerate(root_path.parts[1:]):
                fd, binding = _open_directory_component(
                    parent_fd,
                    component,
                    create=True,
                    operation=operation,
                    label=f"publication root ancestor {index + 1}",
                )
                fds.append(fd)
                bindings.append(binding)
                parent_fd = fd
            root_fd = parent_fd

            def fixed(parent: int, name: str, label: str) -> int:
                fd, binding = _open_directory_component(
                    parent, name, create=True, operation=operation, label=label,
                )
                fds.append(fd)
                bindings.append(binding)
                return fd

            data_fd = fixed(root_fd, "data", "data")
            capital_structure_fd = fixed(data_fd, "capital_structure", "capital-structure")
            share_counts_fd = fixed(
                capital_structure_fd, "share_counts", "share-count publication root",
            )
            base_fd = fixed(share_counts_fd, "v2", "share-count publication v2 base")
            receipts_fd = fixed(base_fd, "receipts", "receipt store")
            generations_fd = fixed(base_fd, "generations", "generation store")
            staging_fd = fixed(base_fd, ".staging", "staging store")
            lane = cls(
                root_path=root_path,
                operation=operation,
                anchor_fd=anchor_fd,
                anchor_identity=_file_identity(anchor_stat),
                fds=fds,
                bindings=bindings,
                root_fd=root_fd,
                data_fd=data_fd,
                capital_structure_fd=capital_structure_fd,
                base_fd=base_fd,
                receipts_fd=receipts_fd,
                generations_fd=generations_fd,
                staging_fd=staging_fd,
            )
            lane.assert_bound(label="publication lane acquisition")
            return lane
        except BaseException:
            for fd in reversed(fds):
                with contextlib.suppress(OSError):
                    os.close(fd)
            raise

    def _assert_directory_binding(self, binding: _DirectoryBinding) -> None:
        try:
            opened = os.fstat(binding.fd)
            linked = os.stat(
                binding.name,
                dir_fd=binding.parent_fd,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise ShareCountPublicationError(
                f"share-count {binding.label} directory was rebound",
            ) from exc
        if (
            not stat.S_ISDIR(opened.st_mode)
            or not stat.S_ISDIR(linked.st_mode)
            or _file_identity(opened) != binding.identity
            or _file_identity(linked) != binding.identity
        ):
            raise ShareCountPublicationError(
                f"share-count {binding.label} directory was rebound",
            )

    def _assert_entry_binding(self, binding: _EntryBinding) -> None:
        try:
            opened = os.fstat(binding.fd)
            linked = os.stat(
                binding.name,
                dir_fd=binding.parent_fd,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise ShareCountPublicationError(
                f"share-count {binding.label} was rebound",
            ) from exc
        if (
            not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(linked.st_mode)
            or _file_identity(opened) != binding.identity
            or _file_identity(linked) != binding.identity
        ):
            raise ShareCountPublicationError(f"share-count {binding.label} was rebound")

    def assert_bound(self, *, label: str, check_deadline: bool = True) -> None:
        if check_deadline:
            self.operation.check(label)
        try:
            anchor = os.fstat(self.anchor_fd)
        except OSError as exc:  # pragma: no cover - held descriptor
            raise ShareCountPublicationError("share-count filesystem root was rebound") from exc
        if not stat.S_ISDIR(anchor.st_mode) or _file_identity(anchor) != self.anchor_identity:
            raise ShareCountPublicationError("share-count filesystem root was rebound")
        for binding in self._bindings:
            if check_deadline:
                self.operation.check(f"{label} directory identity")
            self._assert_directory_binding(binding)
            if check_deadline:
                self.operation.check(f"{label} directory identity")
        if self._lock_binding is not None:
            if check_deadline:
                self.operation.check(f"{label} lock identity")
            self._assert_entry_binding(self._lock_binding)
        if check_deadline:
            self.operation.check(label)

    def attach_lock(self, fd: int, identity: tuple[int, int]) -> None:
        self._lock_binding = _EntryBinding(
            parent_fd=self.base_fd,
            name=LOCK_NAME,
            fd=fd,
            identity=identity,
            label="publication lease path",
        )

    def detach_lock(self) -> None:
        self._lock_binding = None

    def arm_terminal_cleanup(self, *, label: str) -> None:
        """Complete every fallible lease check before journal removal.

        Once armed, the caller may perform only the exact journal unlink and
        return an already-built result.  Lease teardown then becomes
        best-effort and nonthrowing so a successful cleanup cannot be followed
        by an error that falsely claims durable recovery evidence remains.
        """
        if self._terminal_cleanup_armed:
            raise ShareCountPublicationError(
                "share-count terminal journal cleanup was already armed",
            )
        self.assert_bound(label=label)
        self._terminal_cleanup_armed = True

    @contextlib.contextmanager
    def directory(self, parent_fd: int, name: str, *, create: bool, label: str) -> Iterator[int]:
        self.assert_bound(label=f"{label} parent identity")
        fd, binding = _open_directory_component(
            parent_fd, name, create=create, operation=self.operation, label=label,
        )
        try:
            yield fd
        except BaseException:
            raise
        else:
            self._assert_directory_binding(binding)
            self.operation.check(f"{label} directory release")
        finally:
            os.close(fd)

    def close(self) -> None:
        for fd in reversed(self._fds):
            with contextlib.suppress(OSError):
                os.close(fd)
        self._fds.clear()


def _bounded_read_at(
    directory_fd: int,
    name: str,
    *,
    max_bytes: int,
    label: str,
    operation: _OperationDeadline,
    missing_ok: bool = False,
) -> bytes | None:
    name = _entry_name(name, label=label)
    operation.check(f"{label} stat")
    try:
        file_stat = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        operation.check(f"{label} stat")
        if missing_ok:
            return None
        raise ShareCountPublicationError(f"share-count {label} is missing") from None
    except OSError as exc:
        raise ShareCountPublicationError(f"share-count {label} cannot be stated safely") from exc
    operation.check(f"{label} stat")
    if not stat.S_ISREG(file_stat.st_mode):
        raise ShareCountPublicationError(f"share-count {label} is not a regular file")
    if file_stat.st_size < 1 or file_stat.st_size > max_bytes:
        raise ShareCountPublicationTooLarge(f"share-count {label} exceeds byte cap")
    flags = (
        os.O_RDONLY
        | os.O_NONBLOCK
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        fd = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise ShareCountPublicationError(f"share-count {label} cannot be opened safely") from exc
    try:
        opened = os.fstat(fd)
        operation.check(f"{label} open")
        if (
            not stat.S_ISREG(opened.st_mode)
            or _file_identity(opened) != _file_identity(file_stat)
            or opened.st_size != file_stat.st_size
        ):
            raise ShareCountPublicationError(f"share-count {label} changed before bounded read")
        chunks: list[bytes] = []
        observed = 0
        while observed < max_bytes + 1:
            operation.check(f"{label} bounded read")
            chunk = os.read(fd, min(64 * 1024, max_bytes + 1 - observed))
            operation.check(f"{label} bounded read")
            if not chunk:
                break
            chunks.append(chunk)
            observed += len(chunk)
        body = b"".join(chunks)
        final_opened = os.fstat(fd)
        try:
            final_linked = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except OSError as exc:
            raise ShareCountPublicationError(
                f"share-count {label} changed during bounded read",
            ) from exc
        operation.check(f"{label} bounded read verification")
        if (
            not 1 <= len(body) <= max_bytes
            or len(body) != file_stat.st_size
            or _file_identity(final_opened) != _file_identity(file_stat)
            or _file_identity(final_linked) != _file_identity(file_stat)
            or final_opened.st_size != file_stat.st_size
            or final_linked.st_size != file_stat.st_size
        ):
            raise ShareCountPublicationError(f"share-count {label} changed during bounded read")
        return body
    finally:
        os.close(fd)


def _fsync_directory_at(
    directory_fd: int, *, operation: _OperationDeadline, label: str,
) -> None:
    operation.check(f"{label} directory fsync")
    os.fsync(directory_fd)
    operation.check(f"{label} directory fsync")


def _write_all(
    fd: int, body: bytes, *, operation: _OperationDeadline, label: str,
) -> None:
    offset = 0
    while offset < len(body):
        operation.check(f"{label} write")
        written = os.write(fd, body[offset:])
        operation.check(f"{label} write")
        if written <= 0:  # pragma: no cover - regular-file write contract
            raise ShareCountPublicationError(f"share-count {label} write made no progress")
        offset += written


def _write_immutable_at(
    directory_fd: int,
    name: str,
    body: bytes,
    *,
    max_bytes: int,
    label: str,
    operation: _OperationDeadline,
) -> None:
    name = _entry_name(name, label=label)
    if not isinstance(body, bytes) or not 1 <= len(body) <= max_bytes:
        raise ShareCountPublicationTooLarge(f"share-count {label} exceeds byte cap")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | os.O_NONBLOCK
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    operation.check(f"immutable {label} create")
    try:
        fd = os.open(name, flags, 0o600, dir_fd=directory_fd)
    except FileExistsError:
        existing = _bounded_read_at(
            directory_fd,
            name,
            max_bytes=max_bytes,
            label=label,
            operation=operation,
        )
        if existing != body:
            raise ShareCountPublicationConflict(f"share-count immutable {label} already differs")
        return
    except OSError as exc:
        raise ShareCountPublicationError(f"share-count immutable {label} cannot be created") from exc
    try:
        opened = os.fstat(fd)
        operation.check(f"immutable {label} create")
        if not stat.S_ISREG(opened.st_mode):
            raise ShareCountPublicationError(f"share-count immutable {label} is not regular")
        _write_all(fd, body, operation=operation, label=f"immutable {label}")
        operation.check(f"immutable {label} fsync")
        os.fsync(fd)
        operation.check(f"immutable {label} fsync")
    finally:
        os.close(fd)
    _fsync_directory_at(directory_fd, operation=operation, label=f"immutable {label}")
    if _bounded_read_at(
        directory_fd,
        name,
        max_bytes=max_bytes,
        label=label,
        operation=operation,
    ) != body:
        raise ShareCountPublicationError(f"share-count immutable {label} read-back mismatch")


def _open_temporary_at(
    directory_fd: int, *, operation: _OperationDeadline, label: str,
) -> tuple[int, str, tuple[int, int]]:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | os.O_NONBLOCK
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    for _ in range(32):
        operation.check(f"{label} temporary create")
        name = ".share-count-" + secrets.token_hex(16)
        try:
            fd = os.open(name, flags, 0o600, dir_fd=directory_fd)
        except FileExistsError:  # pragma: no cover - cryptographic collision
            continue
        except OSError as exc:
            raise ShareCountPublicationError(
                f"share-count {label} temporary cannot be created",
            ) from exc
        opened = os.fstat(fd)
        operation.check(f"{label} temporary create")
        if not stat.S_ISREG(opened.st_mode):  # pragma: no cover - O_EXCL create
            os.close(fd)
            raise ShareCountPublicationError(f"share-count {label} temporary is unsafe")
        return fd, name, _file_identity(opened)
    raise ShareCountPublicationError(f"share-count {label} temporary name space is exhausted")


def _cleanup_temporary_at(
    directory_fd: int, name: str, identity: tuple[int, int],
) -> None:
    # Cleanup must remain descriptor-relative even when the deadline itself is
    # what interrupted the write.  Never unlink a replacement entry.
    try:
        linked = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if _file_identity(linked) == identity:
            os.unlink(name, dir_fd=directory_fd)
    except FileNotFoundError:
        return
    except OSError:
        return


def _atomic_write_at(
    directory_fd: int,
    name: str,
    body: bytes,
    *,
    expected_previous: bytes | None,
    max_bytes: int,
    label: str,
    operation: _OperationDeadline,
) -> None:
    name = _entry_name(name, label=label)
    if not isinstance(body, bytes) or not 1 <= len(body) <= max_bytes:
        raise ShareCountPublicationTooLarge(f"share-count {label} exceeds byte cap")
    current = _bounded_read_at(
        directory_fd,
        name,
        max_bytes=max_bytes,
        label=label,
        operation=operation,
        missing_ok=True,
    )
    if current != expected_previous:
        raise ShareCountPublicationConflict(f"share-count {label} changed before local CAS")
    fd, temporary, temporary_identity = _open_temporary_at(
        directory_fd, operation=operation, label=label,
    )
    try:
        _write_all(fd, body, operation=operation, label=label)
        operation.check(f"{label} temporary fsync")
        os.fsync(fd)
        operation.check(f"{label} temporary fsync")
        os.close(fd)
        fd = -1
        # Recheck immediately before descriptor-relative replace.  A hostile
        # path rebind can at worst change an entry in this held directory; it
        # can never redirect the write outside it.
        if _bounded_read_at(
            directory_fd,
            name,
            max_bytes=max_bytes,
            label=label,
            operation=operation,
            missing_ok=True,
        ) != expected_previous:
            raise ShareCountPublicationConflict(f"share-count {label} changed before local replace")
        operation.check(f"{label} local replace")
        os.replace(
            temporary,
            name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        operation.check(f"{label} local replace")
        _fsync_directory_at(directory_fd, operation=operation, label=label)
    finally:
        if fd >= 0:
            os.close(fd)
        _cleanup_temporary_at(directory_fd, temporary, temporary_identity)
    if _bounded_read_at(
        directory_fd,
        name,
        max_bytes=max_bytes,
        label=label,
        operation=operation,
    ) != body:
        raise ShareCountPublicationError(f"share-count {label} local read-back mismatch")


def _remove_exact_at(
    directory_fd: int,
    name: str,
    body: bytes,
    *,
    max_bytes: int,
    label: str,
    operation: _OperationDeadline,
) -> None:
    name = _entry_name(name, label=label)
    existing = _bounded_read_at(
        directory_fd,
        name,
        max_bytes=max_bytes,
        label=label,
        operation=operation,
        missing_ok=True,
    )
    if existing is None:
        return
    if existing != body:
        raise ShareCountPublicationError(f"share-count {label} changed before cleanup")
    operation.check(f"{label} unlink")
    try:
        os.unlink(name, dir_fd=directory_fd)
    except OSError as exc:
        raise ShareCountPublicationError(f"share-count {label} changed before cleanup") from exc
    operation.check(f"{label} unlink")
    _fsync_directory_at(directory_fd, operation=operation, label=label)


def _emergency_remove_exact_at(
    directory_fd: int, name: str, body: bytes, *, max_bytes: int,
) -> bool:
    """Bounded descriptor-relative unwind after a definitely pre-CAS failure.

    This cleanup is intentionally allowed after the decision deadline has
    expired.  It cannot turn the operation into success; it only prevents a
    durable ``cas_started`` record from falsely claiming that CAS was invoked.
    """
    name = _entry_name(name, label="pre-CAS cleanup")
    flags = (
        os.O_RDONLY
        | os.O_NONBLOCK
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        linked = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(linked.st_mode)
            or not 1 <= linked.st_size <= max_bytes
        ):
            return False
        fd = os.open(name, flags, dir_fd=directory_fd)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    try:
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or _file_identity(opened) != _file_identity(linked)
            or opened.st_size != linked.st_size
        ):
            return False
        chunks: list[bytes] = []
        observed = 0
        while observed < max_bytes + 1:
            chunk = os.read(fd, min(64 * 1024, max_bytes + 1 - observed))
            if not chunk:
                break
            chunks.append(chunk)
            observed += len(chunk)
        final_linked = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            b"".join(chunks) != body
            or _file_identity(final_linked) != _file_identity(linked)
        ):
            return False
    except OSError:
        return False
    finally:
        os.close(fd)
    try:
        os.unlink(name, dir_fd=directory_fd)
    except OSError:
        return False
    with contextlib.suppress(OSError):
        os.fsync(directory_fd)
    return True


def _abandon_pre_cas_records(
    lane: _PublicationLane,
    *,
    marker_body: bytes,
    capsule_body: bytes,
    alternate_marker_body: bytes | None = None,
) -> None:
    removed = _emergency_remove_exact_at(
        lane.base_fd,
        PENDING_NAME,
        marker_body,
        max_bytes=MAX_PENDING_MARKER_BYTES,
    )
    if not removed and alternate_marker_body is not None:
        removed = _emergency_remove_exact_at(
            lane.base_fd,
            PENDING_NAME,
            alternate_marker_body,
            max_bytes=MAX_PENDING_MARKER_BYTES,
        )
    if removed:
        _emergency_remove_exact_at(
            lane.base_fd,
            RECOVERY_NAME,
            capsule_body,
            max_bytes=MAX_RECOVERY_CAPSULE_BYTES,
        )


@contextlib.contextmanager
def _publication_lease(
    root: Path, *, deadline: float, monotonic: Callable[[], float],
) -> Iterator[_PublicationLane]:
    """Bounded nonblocking cross-process lease covering recovery and publish."""
    try:
        import fcntl
    except ImportError as exc:  # pragma: no cover - supported production hosts are POSIX
        raise ShareCountPublicationError("share-count publication lease is unavailable") from exc
    operation = _OperationDeadline(deadline=deadline, monotonic=monotonic)
    lane = _PublicationLane.open(root, operation=operation)
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | os.O_NONBLOCK
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        operation.check("publication lease open")
        fd = os.open(LOCK_NAME, flags, 0o600, dir_fd=lane.base_fd)
    except OSError as exc:
        lane.close()
        raise ShareCountPublicationError("share-count publication lease path is unsafe") from exc
    completed_normally = False
    try:
        opened = os.fstat(fd)
        try:
            linked = os.stat(LOCK_NAME, dir_fd=lane.base_fd, follow_symlinks=False)
        except OSError as exc:
            raise ShareCountPublicationError("share-count publication lease path is unsafe") from exc
        operation.check("publication lease open")
        if (
            not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(linked.st_mode)
            or _file_identity(opened) != _file_identity(linked)
        ):
            raise ShareCountPublicationError("share-count publication lease path is unsafe")
        lane.attach_lock(fd, _file_identity(opened))
        while True:
            operation.check("publication lease acquisition")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(0.02)
                if monotonic() >= deadline:
                    raise ShareCountPublicationError("share-count publication lease timed out")
        lane.assert_bound(label="publication lease acquisition")
        try:
            yield lane
        except BaseException:
            raise
        else:
            if not lane._terminal_cleanup_armed:
                lane.assert_bound(label="publication lease release")
            completed_normally = True
    finally:
        with contextlib.suppress(Exception):
            fcntl.flock(fd, fcntl.LOCK_UN)
        lane.detach_lock()
        with contextlib.suppress(OSError):
            os.close(fd)
        lane.close()
        if completed_normally and not lane._terminal_cleanup_armed:
            operation.check("publication lease release")


def _stage_ledger(lane: _PublicationLane, ledger: bytes) -> None:
    digest = _sha(ledger)
    name = f"{digest}.ledger"
    lane.assert_bound(label="staged ledger write")
    _write_immutable_at(
        lane.staging_fd,
        name,
        ledger,
        max_bytes=MAX_LEDGER_BYTES,
        label="staged ledger",
        operation=lane.operation,
    )
    observed = _bounded_read_at(
        lane.staging_fd,
        name,
        max_bytes=MAX_LEDGER_BYTES,
        label="staged ledger",
        operation=lane.operation,
    )
    if observed != ledger or _sha(observed) != digest:
        raise ShareCountPublicationError("share-count staged ledger hash mismatch")
    _remove_exact_at(
        lane.staging_fd,
        name,
        ledger,
        max_bytes=MAX_LEDGER_BYTES,
        label="staged ledger",
        operation=lane.operation,
    )
    lane.assert_bound(label="staged ledger cleanup")


def _local_pointer_body(lane: _PublicationLane) -> bytes | None:
    return _bounded_read_at(
        lane.base_fd,
        POINTER_NAME,
        max_bytes=MAX_POINTER_BYTES,
        label="current pointer",
        operation=lane.operation,
        missing_ok=True,
    )


def _read_local_selector(
    lane: _PublicationLane,
    *,
    signer: ShareCountSigner,
    witness: Mapping[str, Any] | None,
) -> _LocalReceiptSelection | None:
    """Authenticate the local pointer and signed receipt without opening its ledger."""
    lane.assert_bound(label="local selector read")
    pointer_body = _local_pointer_body(lane)
    if pointer_body is None:
        return None
    pointer = _validate_pointer(_parse_canonical_json(pointer_body, label="current pointer", max_bytes=MAX_POINTER_BYTES))
    lane.operation.check("current pointer validation")
    if witness is not None and not _pointer_matches_witness(pointer, witness):
        raise ShareCountPublicationError("share-count current pointer is detached from external head")
    receipt_name = _id_digest(
        pointer["receipt_id"], prefix=_RECEIPT_PREFIX, label="pointer receipt",
    ) + ".json"
    receipt_body = _bounded_read_at(
        lane.receipts_fd,
        receipt_name,
        max_bytes=MAX_RECEIPT_BYTES,
        label="immutable receipt",
        operation=lane.operation,
    )
    if _sha(receipt_body) != pointer["receipt_sha256"] or len(receipt_body) != pointer["receipt_byte_length"]:
        raise ShareCountPublicationError("share-count current receipt bytes are detached from pointer")
    receipt = _validate_receipt(_parse_canonical_json(receipt_body, label="immutable receipt", max_bytes=MAX_RECEIPT_BYTES), signer=signer)
    lane.operation.check("immutable receipt validation")
    _verify_receipt_matches_witness(receipt, receipt_body, witness) if witness is not None else None
    if pointer != _pointer_for(receipt=receipt, receipt_body=receipt_body):
        raise ShareCountPublicationError("share-count current receipt is detached from pointer")
    lane.assert_bound(label="local selector verification")
    return _LocalReceiptSelection(
        receipt=receipt,
        receipt_body=receipt_body,
        pointer=pointer,
    )


def _load_local_result(
    lane: _PublicationLane,
    *,
    selection: _LocalReceiptSelection,
    published: bool = False,
    recovered: bool = False,
) -> ShareCountPublicationResult:
    """Open and validate the one ledger chosen by an authenticated local selector."""
    receipt = selection.receipt
    pointer = selection.pointer
    generation_name = _id_digest(
        pointer["generation_id"], prefix=_GENERATION_PREFIX, label="pointer generation",
    )
    with lane.directory(
        lane.generations_fd,
        generation_name,
        create=False,
        label="selected generation",
    ) as generation_fd:
        ledger = _bounded_read_at(
            generation_fd,
            "ledger.json",
            max_bytes=MAX_LEDGER_BYTES,
            label="immutable ledger",
            operation=lane.operation,
        )
    generation = receipt["generation"]
    if _sha(ledger) != generation["ledger_sha256"] or len(ledger) != generation["ledger_byte_length"]:
        raise ShareCountPublicationError("share-count immutable ledger is detached from receipt")
    _parse_canonical_json(ledger, label="immutable ledger", max_bytes=MAX_LEDGER_BYTES)
    lane.operation.check("immutable ledger validation")
    lane.assert_bound(label="local ledger verification")
    ledger_path = _local_base(lane.root_path) / "generations" / generation_name / "ledger.json"
    return ShareCountPublicationResult(
        receipt=receipt, pointer=pointer, ledger_path=ledger_path, ledger_bytes=ledger,
        published=published, recovered=recovered,
    )


def _verify_receipt_matches_witness(receipt: Mapping[str, Any], receipt_body: bytes, witness: Mapping[str, Any] | None) -> None:
    if witness is None:
        return
    if not (
        receipt["receipt_id"] == witness["receipt_id"]
        and receipt["sequence"] == witness["sequence"]
        and _sha(receipt_body) == witness["receipt_sha256"]
        and len(receipt_body) == witness["receipt_byte_length"]
        and receipt["generation"]["generation_id"] == witness["generation_id"]
        and receipt["generation"]["ledger_sha256"] == witness["ledger_sha256"]
        and receipt["generation"]["ledger_byte_length"] == witness["ledger_byte_length"]
        and receipt["published_at"] == witness["published_at"]
        and receipt["previous_receipt"] == witness["previous_receipt"]
    ):
        raise ShareCountPublicationError("share-count receipt is detached from external head")


def _guard_call(
    lane: _PublicationLane,
    *,
    label: str,
    call: Callable[..., Any],
    args: Sequence[Any] = (),
    kwargs: Mapping[str, Any] | None = None,
) -> Any:
    lane.assert_bound(label=f"before {label}")
    owner = getattr(call, "__self__", None)
    bind_deadline = getattr(owner, "_bind_deadline", None)
    deadline_context = (
        bind_deadline(lane.operation) if callable(bind_deadline) else contextlib.nullcontext()
    )
    with deadline_context:
        result = lane.operation.run(label, call, *args, **dict(kwargs or {}))
    lane.assert_bound(label=f"after {label}")
    return result


def _read_selected_external_receipt(
    lane: _PublicationLane,
    head: Mapping[str, Any],
    *,
    guard: ShareCountHeadGuard,
    signer: ShareCountSigner,
) -> tuple[dict[str, Any], bytes]:
    """Authenticate the externally selected receipt without opening its ledger."""
    _validate_any_head_witness(
        head,
        signer=signer,
        expected_scope=(guard.guard_scope if head.get("schema") == WITNESS_V3_SCHEMA else None),
    )
    lane.operation.check("external head validation")
    body = _guard_call(
        lane,
        label="external selected receipt read",
        call=guard.read_artifact,
        kwargs={
            "key": head["receipt_object_key"],
            "max_bytes": MAX_RECEIPT_BYTES,
        },
    )
    if _sha(body) != head["receipt_sha256"] or len(body) != head["receipt_byte_length"]:
        raise ShareCountPublicationError("share-count external receipt bytes mismatch")
    latest = _validate_receipt(
        _parse_canonical_json(body, label="external receipt", max_bytes=MAX_RECEIPT_BYTES),
        signer=signer,
    )
    lane.operation.check("external receipt validation")
    _verify_receipt_matches_witness(latest, body, head)
    return latest, body


def _read_selected_external_ledger(
    lane: _PublicationLane,
    head: Mapping[str, Any],
    *,
    receipt: Mapping[str, Any],
    receipt_body: bytes,
    guard: ShareCountHeadGuard,
    signer: ShareCountSigner,
) -> bytes:
    """Read the selected external ledger after all selector proofs have passed."""
    head = _validate_any_head_witness(
        head,
        signer=signer,
        expected_scope=(guard.guard_scope if head.get("schema") == WITNESS_V3_SCHEMA else None),
    )
    receipt = _validate_receipt(receipt, signer=signer)
    if receipt_body != _canonical_bytes(dict(receipt)) + b"\n":
        raise ShareCountPublicationError("share-count selected external receipt body is detached")
    _verify_receipt_matches_witness(receipt, receipt_body, head)
    lane.operation.check("selected external ledger preflight")
    ledger = _guard_call(
        lane,
        label="external ledger read",
        call=guard.read_artifact,
        kwargs={"key": head["ledger_object_key"], "max_bytes": MAX_LEDGER_BYTES},
    )
    if _sha(ledger) != receipt["generation"]["ledger_sha256"] or len(ledger) != receipt["generation"]["ledger_byte_length"]:
        raise ShareCountPublicationError("share-count external ledger bytes mismatch")
    _parse_canonical_json(ledger, label="external ledger", max_bytes=MAX_LEDGER_BYTES)
    lane.operation.check("external ledger validation")
    return ledger


def _read_external_receipt_ref(
    lane: _PublicationLane,
    reference: Mapping[str, Any],
    *,
    guard: ShareCountHeadGuard,
    signer: ShareCountSigner,
    label: str,
) -> tuple[dict[str, Any], bytes]:
    normalized = _validate_receipt_ref(reference, label=label)
    body = _guard_call(
        lane,
        label=f"{label} read",
        call=guard.read_artifact,
        kwargs={
            "key": _receipt_external_key(normalized["receipt_id"]),
            "max_bytes": MAX_RECEIPT_BYTES,
        },
    )
    if (
        _sha(body) != normalized["receipt_sha256"]
        or len(body) != normalized["receipt_byte_length"]
    ):
        raise ShareCountPublicationError(f"share-count {label} bytes mismatch")
    receipt = _validate_receipt(
        _parse_canonical_json(body, label=label, max_bytes=MAX_RECEIPT_BYTES),
        signer=signer,
    )
    lane.operation.check(f"{label} validation")
    if _receipt_ref(receipt, body) != normalized:
        raise ShareCountPublicationError(f"share-count {label} identity mismatch")
    return receipt, body


def _build_ancestor_refs(
    lane: _PublicationLane,
    *,
    predecessor: Mapping[str, Any],
    predecessor_body: bytes,
    candidate_sequence: int,
    guard: ShareCountHeadGuard,
    signer: ShareCountSigner,
) -> list[dict[str, Any]]:
    """Derive a bounded binary-lifting table from authenticated receipts."""
    if (
        isinstance(candidate_sequence, bool)
        or not isinstance(candidate_sequence, int)
        or not 2 <= candidate_sequence <= MAX_RECEIPT_SEQUENCE
        or predecessor.get("sequence") != candidate_sequence - 1
    ):
        raise ShareCountPublicationError(
            "share-count binary-lifting predecessor sequence is invalid",
        )
    predecessor_ref = _receipt_ref(predecessor, predecessor_body)
    _validate_receipt_ref(
        predecessor_ref,
        label="publication predecessor",
        expected_sequence=candidate_sequence - 1,
    )
    ancestors = [predecessor_ref]
    cached: dict[str, tuple[dict[str, Any], bytes]] = {
        predecessor_ref["receipt_id"]: (dict(predecessor), predecessor_body),
    }
    ancestor_count = (candidate_sequence - 1).bit_length()
    if ancestor_count > MAX_ANCESTOR_REFS:
        raise ShareCountPublicationTooLarge(
            "share-count binary-lifting table exceeds its protocol bound",
        )
    for level in range(1, ancestor_count):
        lane.operation.check("binary-lifting receipt construction")
        half_ref = ancestors[level - 1]
        loaded = cached.get(half_ref["receipt_id"])
        if loaded is None:
            loaded = _read_external_receipt_ref(
                lane,
                half_ref,
                guard=guard,
                signer=signer,
                label=f"publication ancestor level {level - 1}",
            )
            cached[half_ref["receipt_id"]] = loaded
        half_receipt, half_body = loaded
        if _receipt_ref(half_receipt, half_body) != half_ref:
            raise ShareCountPublicationError(
                "share-count binary-lifting ancestor is detached",
            )
        half_ancestors = half_receipt.get("ancestor_refs")
        if not isinstance(half_ancestors, list) or level - 1 >= len(half_ancestors):
            raise ShareCountPublicationError(
                "share-count binary-lifting ancestor table is malformed",
            )
        derived = _validate_receipt_ref(
            half_ancestors[level - 1],
            label=f"publication ancestor level {level}",
            expected_sequence=candidate_sequence - (1 << level),
        )
        ancestors.append(derived)
    return ancestors


def _assert_local_high_water(
    local: _LocalReceiptSelection | ShareCountPublicationResult | None,
    head: Mapping[str, Any] | None,
) -> None:
    """Never replace an authenticated retained selector with a replay/fork."""
    if local is None:
        return
    if head is None:
        raise ShareCountPublicationError(
            "share-count external head is below authenticated local high-water",
        )
    local_sequence = local.sequence
    external_sequence = int(head["sequence"])
    if external_sequence < local_sequence:
        raise ShareCountPublicationError(
            "share-count external head rollback is below authenticated local high-water",
        )
    if external_sequence == local_sequence:
        if not _pointer_matches_witness(local.pointer, head):
            raise ShareCountPublicationError(
                "share-count external head forks authenticated local high-water",
            )
        local_receipt_body = (
            local.receipt_body
            if isinstance(local, _LocalReceiptSelection)
            else _canonical_bytes(dict(local.receipt)) + b"\n"
        )
        _verify_receipt_matches_witness(local.receipt, local_receipt_body, head)
        return


def _prove_local_high_water(
    lane: _PublicationLane,
    *,
    local: _LocalReceiptSelection | ShareCountPublicationResult | None,
    head: Mapping[str, Any],
    head_receipt: Mapping[str, Any],
    head_receipt_body: bytes,
    guard: ShareCountHeadGuard,
    signer: ShareCountSigner,
) -> None:
    if local is None or local.sequence == head["sequence"]:
        return
    if local.sequence > head["sequence"]:
        raise ShareCountPublicationError(
            "share-count external head rollback is below authenticated local high-water",
        )
    current = dict(head_receipt)
    current_body = head_receipt_body
    target = {
        "sequence": local.sequence,
        "receipt_id": local.receipt_id,
        "receipt_sha256": local.pointer["receipt_sha256"],
        "receipt_byte_length": local.pointer["receipt_byte_length"],
    }
    reads = 0
    while current["sequence"] > local.sequence:
        lane.operation.check("binary-lifting local high-water proof")
        delta = current["sequence"] - local.sequence
        level = delta.bit_length() - 1
        ancestors = current.get("ancestor_refs")
        if not isinstance(ancestors, list) or level >= len(ancestors):
            raise ShareCountPublicationError(
                "share-count external binary-lifting proof is malformed",
            )
        reference = _validate_receipt_ref(
            ancestors[level],
            label=f"high-water ancestor level {level}",
            expected_sequence=current["sequence"] - (1 << level),
        )
        if reference["sequence"] == local.sequence:
            if reference != target:
                raise ShareCountPublicationError(
                    "share-count external ancestry diverges from authenticated local high-water",
                )
            return
        current, current_body = _read_external_receipt_ref(
            lane,
            reference,
            guard=guard,
            signer=signer,
            label="high-water skip receipt",
        )
        reads += 1
        if reads >= MAX_ANCESTOR_REFS:
            raise ShareCountPublicationError(
                "share-count external binary-lifting proof exceeds logarithmic bound",
            )
    if _receipt_ref(current, current_body) != target:
        raise ShareCountPublicationError(
            "share-count external ancestry diverges from authenticated local high-water",
        )


def _prove_pending_expected_high_water(
    lane: _PublicationLane,
    *,
    expected: Mapping[str, Any],
    head: Mapping[str, Any],
    head_receipt: Mapping[str, Any],
    head_receipt_body: bytes,
    guard: ShareCountHeadGuard,
    signer: ShareCountSigner,
) -> None:
    """Require a selected successor to descend from a pending expected head.

    A local pointer may be lost in the same crash that preserved a signed
    marker.  Its ``expected_witness`` is then a temporary authenticated
    high-water: accepting a different selected head without an O(log n)
    ancestry proof would permit a signed external fork to bypass that state.
    """
    expected = _validate_head_witness(expected, signer=signer)
    target = _head_receipt_ref(expected)
    if head["sequence"] < expected["sequence"]:
        raise ShareCountPublicationError(
            "share-count external head rollback is below pending expected high-water",
        )
    if head["sequence"] == expected["sequence"]:
        if _head_receipt_ref(head) != target:
            raise ShareCountPublicationError(
                "share-count external head forks pending expected high-water",
            )
        return
    current = dict(head_receipt)
    current_body = head_receipt_body
    reads = 0
    while current["sequence"] > expected["sequence"]:
        lane.operation.check("binary-lifting pending expected high-water proof")
        delta = current["sequence"] - expected["sequence"]
        level = delta.bit_length() - 1
        ancestors = current.get("ancestor_refs")
        if not isinstance(ancestors, list) or level >= len(ancestors):
            raise ShareCountPublicationError(
                "share-count external binary-lifting pending proof is malformed",
            )
        reference = _validate_receipt_ref(
            ancestors[level],
            label=f"pending high-water ancestor level {level}",
            expected_sequence=current["sequence"] - (1 << level),
        )
        if reference["sequence"] == expected["sequence"]:
            if reference != target:
                raise ShareCountPublicationError(
                    "share-count external ancestry diverges from pending expected high-water",
                )
            return
        current, current_body = _read_external_receipt_ref(
            lane,
            reference,
            guard=guard,
            signer=signer,
            label="pending high-water skip receipt",
        )
        reads += 1
        if reads >= MAX_ANCESTOR_REFS:
            raise ShareCountPublicationError(
                "share-count external binary-lifting pending proof exceeds logarithmic bound",
            )
    if _receipt_ref(current, current_body) != target:
        raise ShareCountPublicationError(
            "share-count external ancestry diverges from pending expected high-water",
        )


def _install_external_bundle(
    lane: _PublicationLane,
    *,
    head: Mapping[str, Any],
    receipt: Mapping[str, Any],
    receipt_body: bytes,
    ledger: bytes,
    expected_pointer: bytes | None,
) -> ShareCountPublicationResult:
    latest, latest_body = receipt, receipt_body
    lane.assert_bound(label="external bundle installation")
    # V2 clean recovery deliberately installs only the selected immutable
    # receipt and ledger.  Skip-proof ancestors remain external until a local
    # high-water comparison or the next receipt construction needs them.
    receipt_name = _id_digest(
        latest["receipt_id"], prefix=_RECEIPT_PREFIX, label="recovered receipt",
    ) + ".json"
    _write_immutable_at(
        lane.receipts_fd,
        receipt_name,
        latest_body,
        max_bytes=MAX_RECEIPT_BYTES,
        label="recovered receipt",
        operation=lane.operation,
    )
    generation = latest["generation"]
    generation_name = _id_digest(
        generation["generation_id"], prefix=_GENERATION_PREFIX, label="recovered generation",
    )
    with lane.directory(
        lane.generations_fd,
        generation_name,
        create=True,
        label="recovered generation",
    ) as generation_fd:
        _write_immutable_at(
            generation_fd,
            "ledger.json",
            ledger,
            max_bytes=MAX_LEDGER_BYTES,
            label="recovered ledger",
            operation=lane.operation,
        )
    ledger_path = _local_base(lane.root_path) / "generations" / generation_name / "ledger.json"
    pointer = _pointer_for(receipt=latest, receipt_body=latest_body)
    if not _pointer_matches_witness(pointer, head):
        raise ShareCountPublicationError("share-count recovered pointer is detached from head")
    pointer_body = _canonical_bytes(pointer) + b"\n"
    _atomic_write_at(
        lane.base_fd,
        POINTER_NAME,
        pointer_body,
        expected_previous=expected_pointer,
        max_bytes=MAX_POINTER_BYTES,
        label="current pointer",
        operation=lane.operation,
    )
    lane.assert_bound(label="external bundle installation")
    return ShareCountPublicationResult(receipt=latest, pointer=pointer, ledger_path=ledger_path, ledger_bytes=ledger, published=False, recovered=True)


def _journal(
    *,
    expected: Mapping[str, Any] | None,
    candidate: Mapping[str, Any],
    expected_pointer: bytes | None,
    candidate_pointer: bytes,
    signer: ShareCountSigner,
) -> dict[str, Any]:
    """Build the one-write durable commit intent for a v2 head transition."""
    record: dict[str, Any] = {
        "schema": JOURNAL_SCHEMA,
        "key_id": signer.key_id,
        "expected_witness": dict(expected) if expected is not None else None,
        "candidate_witness": dict(candidate),
        "expected_pointer_b64": (
            base64.b64encode(expected_pointer).decode("ascii")
            if expected_pointer is not None
            else None
        ),
        "candidate_pointer_b64": base64.b64encode(candidate_pointer).decode("ascii"),
        "signature": "",
    }
    sign = getattr(signer, "sign_journal", None)
    if not callable(sign):
        raise ShareCountPublicationError("share-count publish journal signer is unavailable")
    record["signature"] = sign(_journal_payload(record))
    return _validate_journal(record, signer=signer)


def _validate_journal(
    record: Mapping[str, Any], *, signer: ShareCountSigner,
) -> dict[str, Any]:
    required = {
        "schema", "key_id", "expected_witness", "candidate_witness",
        "expected_pointer_b64", "candidate_pointer_b64", "signature",
    }
    verify = getattr(signer, "verify_journal", None)
    if (
        not isinstance(record, Mapping)
        or set(record) != required
        or record.get("schema") != JOURNAL_SCHEMA
        or not isinstance(record.get("key_id"), str)
        or not callable(verify)
        or not verify(
            _journal_payload(record),
            record.get("signature"),
            key_id=record["key_id"],
        )
    ):
        raise ShareCountPublicationError(
            "share-count publish journal authentication mismatch",
        )
    _validate_contract(
        record,
        "capital_structure_share_count_publish_journal.schema.json",
        label="publish journal",
    )
    expected = record.get("expected_witness")
    candidate = record.get("candidate_witness")
    if expected is not None and not isinstance(expected, Mapping):
        raise ShareCountPublicationError(
            "share-count publish journal predecessor witness is invalid",
        )
    if not isinstance(candidate, Mapping):
        raise ShareCountPublicationError(
            "share-count publish journal candidate witness is invalid",
        )
    _validate_head_transition(
        previous=expected,
        candidate=candidate,
        signer=signer,
    )
    _validate_embedded_pointer_transition(
        expected=expected,
        candidate=candidate,
        expected_pointer_b64=record.get("expected_pointer_b64"),
        candidate_pointer_b64=record.get("candidate_pointer_b64"),
        label="publish journal",
    )
    return dict(record)


def _capsule(*, expected: Mapping[str, Any] | None, candidate: Mapping[str, Any], expected_pointer: bytes | None, candidate_pointer: bytes, signer: ShareCountSigner) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema": RECOVERY_SCHEMA,
        "key_id": signer.key_id,
        "expected_witness": dict(expected) if expected is not None else None,
        "candidate_witness": dict(candidate),
        "expected_receipt_id": expected["receipt_id"] if expected is not None else None,
        "candidate_receipt_id": candidate["receipt_id"],
        "expected_pointer_sha256": _sha(expected_pointer) if expected_pointer is not None else None,
        "candidate_pointer_sha256": _sha(candidate_pointer),
        "expected_pointer_b64": base64.b64encode(expected_pointer).decode("ascii") if expected_pointer is not None else None,
        "candidate_pointer_b64": base64.b64encode(candidate_pointer).decode("ascii"),
    }
    record["signature"] = signer.sign(_recovery_payload(record))
    _validate_capsule(record, signer=signer, expected=expected, candidate=candidate)
    return record


def _validate_capsule(record: Mapping[str, Any], *, signer: ShareCountSigner, expected: Mapping[str, Any] | None | object = ..., candidate: Mapping[str, Any] | object = ...) -> dict[str, Any]:
    required = {"schema", "key_id", "expected_witness", "candidate_witness", "expected_receipt_id", "candidate_receipt_id", "expected_pointer_sha256", "candidate_pointer_sha256", "expected_pointer_b64", "candidate_pointer_b64", "signature"}
    if not isinstance(record, Mapping) or set(record) != required or record.get("schema") != RECOVERY_SCHEMA or not isinstance(record.get("key_id"), str) or not signer.verify(_recovery_payload(record), record.get("signature"), key_id=record["key_id"]):
        raise ShareCountPublicationError("share-count recovery capsule authentication mismatch")
    recorded_expected = record.get("expected_witness")
    recorded_candidate = record.get("candidate_witness")
    if recorded_expected is not None and not isinstance(recorded_expected, Mapping):
        raise ShareCountPublicationError("share-count recovery capsule predecessor witness is invalid")
    if not isinstance(recorded_candidate, Mapping):
        raise ShareCountPublicationError("share-count recovery capsule candidate witness is invalid")
    _validate_head_transition(
        previous=recorded_expected,
        candidate=recorded_candidate,
        signer=signer,
    )
    previous_body, previous_pointer = _decode_embedded_pointer(
        record["expected_pointer_b64"],
        label="recovery capsule predecessor",
    )
    candidate_body, candidate_pointer = _decode_embedded_pointer(
        record["candidate_pointer_b64"],
        label="recovery capsule candidate",
    )
    if candidate_body is None or _sha(candidate_body) != record["candidate_pointer_sha256"] or (previous_body is None) != (record["expected_pointer_sha256"] is None) or (previous_body is not None and _sha(previous_body) != record["expected_pointer_sha256"]):
        raise ShareCountPublicationError("share-count recovery capsule pointer digest is invalid")
    _validate_embedded_pointer_transition(
        expected=recorded_expected,
        candidate=recorded_candidate,
        expected_pointer_b64=record["expected_pointer_b64"],
        candidate_pointer_b64=record["candidate_pointer_b64"],
        label="recovery capsule",
    )
    if (
        record["candidate_receipt_id"] != candidate_pointer["receipt_id"]
        or record["candidate_receipt_id"] != recorded_candidate["receipt_id"]
    ):
        raise ShareCountPublicationError("share-count recovery capsule candidate is detached")
    if previous_body is not None:
        assert previous_pointer is not None
        if (
            record["expected_receipt_id"] != previous_pointer["receipt_id"]
            or record["expected_receipt_id"] != recorded_expected["receipt_id"]
        ):
            raise ShareCountPublicationError("share-count recovery capsule predecessor is detached")
    elif record["expected_receipt_id"] is not None or recorded_expected is not None:
        raise ShareCountPublicationError("share-count recovery capsule genesis is detached")
    if expected is not ... and recorded_expected != expected:
        raise ShareCountPublicationError("share-count recovery capsule expected head is detached")
    if candidate is not ... and recorded_candidate != candidate:
        raise ShareCountPublicationError("share-count recovery capsule candidate head is detached")
    return dict(record)


def _write_signed_record(
    lane: _PublicationLane,
    name: str,
    record: Mapping[str, Any],
    *,
    max_bytes: int,
    label: str,
) -> bytes:
    body = _canonical_bytes(dict(record)) + b"\n"
    lane.operation.check(f"{label} encoding")
    previous = _bounded_read_at(
        lane.base_fd,
        name,
        max_bytes=max_bytes,
        label=label,
        operation=lane.operation,
        missing_ok=True,
    )
    _atomic_write_at(
        lane.base_fd,
        name,
        body,
        expected_previous=previous,
        max_bytes=max_bytes,
        label=label,
        operation=lane.operation,
    )
    return body


def _write_publish_journal(
    lane: _PublicationLane, record: Mapping[str, Any],
) -> bytes:
    """Durably link a fully fsynced journal into an absent-only pathname.

    The target is never replaced.  A hostile or stale existing entry is
    evidence, not something a new publisher may normalize away.
    """
    body = _canonical_bytes(dict(record)) + b"\n"
    if not 1 <= len(body) <= MAX_PUBLISH_JOURNAL_BYTES:
        raise ShareCountPublicationTooLarge("share-count publish journal exceeds byte cap")
    lane.operation.check("publish journal encoding")
    if _bounded_read_at(
        lane.base_fd,
        JOURNAL_NAME,
        max_bytes=MAX_PUBLISH_JOURNAL_BYTES,
        label="publish journal",
        operation=lane.operation,
        missing_ok=True,
    ) is not None:
        raise ShareCountPublicationConflict(
            "share-count publish journal already exists",
        )
    fd, temporary, temporary_identity = _open_temporary_at(
        lane.base_fd,
        operation=lane.operation,
        label="publish journal",
    )
    linked = False
    try:
        _write_all(fd, body, operation=lane.operation, label="publish journal")
        lane.operation.check("publish journal temporary fsync")
        os.fsync(fd)
        lane.operation.check("publish journal temporary fsync")
        os.close(fd)
        fd = -1
        lane.assert_bound(label="publish journal absent-only link")
        lane.operation.check("publish journal absent-only link")
        try:
            os.link(
                temporary,
                JOURNAL_NAME,
                src_dir_fd=lane.base_fd,
                dst_dir_fd=lane.base_fd,
                follow_symlinks=False,
            )
            linked = True
        except FileExistsError as exc:
            raise ShareCountPublicationConflict(
                "share-count publish journal appeared before durable create",
            ) from exc
        except OSError as exc:
            raise ShareCountPublicationError(
                "share-count publish journal cannot be created safely",
            ) from exc
        _fsync_directory_at(
            lane.base_fd,
            operation=lane.operation,
            label="publish journal create",
        )
    finally:
        if fd >= 0:
            os.close(fd)
        _cleanup_temporary_at(lane.base_fd, temporary, temporary_identity)
        if linked:
            # Persisting cleanup of the temporary hard link is hygiene only;
            # the named journal was already durable before this point.
            _fsync_directory_at(
                lane.base_fd,
                operation=lane.operation,
                label="publish journal temporary cleanup",
            )
    if _bounded_read_at(
        lane.base_fd,
        JOURNAL_NAME,
        max_bytes=MAX_PUBLISH_JOURNAL_BYTES,
        label="publish journal",
        operation=lane.operation,
    ) != body:
        raise ShareCountPublicationError(
            "share-count publish journal exact read-back mismatch",
        )
    return body


def _emergency_restore_publish_journal(
    lane: _PublicationLane, body: bytes,
) -> bool:
    """Best-effort exact evidence restoration after cleanup fault injection."""
    flags = (
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NONBLOCK | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        existing = _emergency_read_exact_at(
            lane.base_fd,
            JOURNAL_NAME,
            max_bytes=MAX_PUBLISH_JOURNAL_BYTES,
        )
        if existing is not None:
            return existing == body
        temporary = ".share-count-journal-restore-" + secrets.token_hex(16)
        fd = os.open(temporary, flags, 0o600, dir_fd=lane.base_fd)
        try:
            offset = 0
            while offset < len(body):
                written = os.write(fd, body[offset:])
                if written <= 0:
                    return False
                offset += written
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.link(
                temporary,
                JOURNAL_NAME,
                src_dir_fd=lane.base_fd,
                dst_dir_fd=lane.base_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            pass
        finally:
            _emergency_remove_exact_at(
                lane.base_fd,
                temporary,
                body,
                max_bytes=MAX_PUBLISH_JOURNAL_BYTES,
            )
        os.fsync(lane.base_fd)
        return _emergency_read_exact_at(
            lane.base_fd,
            JOURNAL_NAME,
            max_bytes=MAX_PUBLISH_JOURNAL_BYTES,
        ) == body
    except OSError:
        return False


def _emergency_read_exact_at(
    directory_fd: int, name: str, *, max_bytes: int,
) -> bytes | None:
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        linked = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(linked.st_mode) or not 1 <= linked.st_size <= max_bytes:
            return b""
        fd = os.open(name, flags, dir_fd=directory_fd)
    except FileNotFoundError:
        return None
    except OSError:
        return b""
    try:
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or _file_identity(opened) != _file_identity(linked)
            or opened.st_size != linked.st_size
        ):
            return b""
        chunks: list[bytes] = []
        observed = 0
        while observed < max_bytes + 1:
            chunk = os.read(fd, min(64 * 1024, max_bytes + 1 - observed))
            if not chunk:
                break
            chunks.append(chunk)
            observed += len(chunk)
        body = b"".join(chunks)
        final_opened = os.fstat(fd)
        try:
            final_linked = os.stat(
                name,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except OSError:
            return b""
        if (
            not 1 <= len(body) <= max_bytes
            or len(body) != linked.st_size
            or not stat.S_ISREG(final_opened.st_mode)
            or not stat.S_ISREG(final_linked.st_mode)
            or _file_identity(final_opened) != _file_identity(linked)
            or _file_identity(final_linked) != _file_identity(linked)
            or final_opened.st_size != linked.st_size
            or final_linked.st_size != linked.st_size
        ):
            return b""
        return body
    except OSError:
        return b""
    finally:
        os.close(fd)


def _clear_publish_journal(lane: _PublicationLane, body: bytes) -> None:
    if not lane._terminal_cleanup_armed:
        raise ShareCountPublicationError(
            "share-count publish journal cleanup was not terminally armed",
        )
    try:
        _remove_exact_at(
            lane.base_fd,
            JOURNAL_NAME,
            body,
            max_bytes=MAX_PUBLISH_JOURNAL_BYTES,
            label="publish journal",
            operation=lane.operation,
        )
    except BaseException as exc:  # noqa: BLE001 - retain commit evidence on every caught failure
        retained = _emergency_restore_publish_journal(lane, body)
        if not retained:
            raise ShareCountPublishIndeterminate(
                "share-count publish journal cleanup failed and exact evidence could not be restored",
            ) from exc
        raise ShareCountPublishIndeterminate(
            "share-count publish journal cleanup failed; exact evidence retained",
        ) from exc


def _read_signed_record(
    lane: _PublicationLane, name: str, *, max_bytes: int, label: str,
) -> tuple[dict[str, Any], bytes] | None:
    body = _bounded_read_at(
        lane.base_fd,
        name,
        max_bytes=max_bytes,
        label=label,
        operation=lane.operation,
        missing_ok=True,
    )
    if body is None:
        return None
    return _decode_signed_record(body, max_bytes=max_bytes, label=label, lane=lane)


def _decode_signed_record(
    body: bytes,
    *,
    max_bytes: int,
    label: str,
    lane: _PublicationLane,
) -> tuple[dict[str, Any], bytes]:
    parsed = _parse_canonical_json(body, label=label, max_bytes=max_bytes)
    lane.operation.check(f"{label} decoding")
    return parsed, body


def _read_authenticated_head(
    lane: _PublicationLane,
    *,
    guard: ShareCountHeadGuard,
    signer: ShareCountSigner,
    label: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Read the mutable selector once, preserving the guard's CAS token."""
    head, token = _guard_call(lane, label=label, call=guard.read)
    if head is not None:
        expected_scope = None
        if head.get("schema") == WITNESS_V3_SCHEMA:
            expected_scope = guard.guard_scope
        head = _validate_any_head_witness(
            head,
            signer=signer,
            expected_scope=expected_scope,
        )
        lane.operation.check(f"{label} validation")
    return head, token


def _maybe_migrate_head_v3(
    lane: _PublicationLane,
    *,
    current: ShareCountPublicationResult | None,
    trace: _RecoveryTrace,
    guard: ShareCountHeadGuard,
    signer: ShareCountSigner,
    enabled: bool,
) -> Mapping[str, Any] | None:
    """Replace one clean v2 selector with a scope-bound same-selection v3 fence."""
    entry_head = trace.selected_head
    if not enabled or trace.recovery_seen_at_entry:
        return entry_head
    if entry_head is None:
        if current is not None:
            raise ShareCountPublicationError(
                "share-count v3 migration found local state without an external head",
            )
        return None
    if entry_head.get("schema") == WITNESS_V3_SCHEMA:
        if current is None or not _pointer_matches_witness(current.pointer, entry_head):
            raise ShareCountPublicationError(
                "share-count v3 head is detached from the recovered local selector",
            )
        return entry_head
    entry_head = _validate_head_witness(entry_head, signer=signer)
    journal_after_recovery = _bounded_read_at(
        lane.base_fd,
        JOURNAL_NAME,
        max_bytes=MAX_PUBLISH_JOURNAL_BYTES,
        label="post-recovery publish journal",
        operation=lane.operation,
        missing_ok=True,
    )
    marker_after_recovery = _bounded_read_at(
        lane.base_fd,
        PENDING_NAME,
        max_bytes=MAX_PENDING_MARKER_BYTES,
        label="post-recovery pending marker",
        operation=lane.operation,
        missing_ok=True,
    )
    capsule_after_recovery = _bounded_read_at(
        lane.base_fd,
        RECOVERY_NAME,
        max_bytes=MAX_RECOVERY_CAPSULE_BYTES,
        label="post-recovery recovery capsule",
        operation=lane.operation,
        missing_ok=True,
    )
    if (
        journal_after_recovery is not None
        or marker_after_recovery is not None
        or capsule_after_recovery is not None
    ):
        raise ShareCountPublishIndeterminate(
            "share-count v3 migration requires exact post-recovery recovery-record absence",
        )
    if current is None or not _pointer_matches_witness(current.pointer, entry_head):
        raise ShareCountPublicationError(
            "share-count v3 migration requires an exact recovered local selector",
        )
    current_receipt_body = _canonical_bytes(dict(current.receipt)) + b"\n"
    _verify_receipt_matches_witness(current.receipt, current_receipt_body, entry_head)
    scope = guard.guard_scope
    candidate = _migrated_head_witness_v3(
        entry_head,
        signer=signer,
        guard_scope=scope,
    )
    fresh, token = _read_authenticated_head(
        lane,
        guard=guard,
        signer=signer,
        label="v3 migration fresh v2 head read",
    )
    if fresh == candidate:
        trace.selected_head = dict(candidate)
        return candidate
    if fresh != entry_head or not isinstance(token, str) or not token:
        raise ShareCountPublicationConflict(
            "share-count v3 migration lost the fresh v2 selector race",
        )
    lane.assert_bound(label="before v3 head migration CAS")
    try:
        owner = getattr(guard.migrate_v2_to_v3, "__self__", None)
        bind_deadline = getattr(owner, "_bind_deadline", None)
        deadline_context = (
            bind_deadline(lane.operation)
            if callable(bind_deadline)
            else contextlib.nullcontext()
        )
        with deadline_context:
            guard.migrate_v2_to_v3(
                expected=entry_head,
                expected_token=token,
                candidate=candidate,
            )
    except ShareCountPublicationConflict:
        # A concurrent byte-identical migration is success; every newer or
        # differently scoped/authenticated selector is an abort.
        pass
    lane.assert_bound(label="after v3 head migration CAS", check_deadline=False)
    confirmed, _ = _read_authenticated_head(
        lane,
        guard=guard,
        signer=signer,
        label="v3 migration confirmation head read",
    )
    if confirmed != candidate:
        raise ShareCountPublicationConflict(
            "share-count v3 migration confirmation selected a different head",
        )
    trace.selected_head = dict(candidate)
    return candidate


def _replay_cas_started_transition(
    lane: _PublicationLane,
    *,
    expected: Mapping[str, Any] | None,
    candidate: Mapping[str, Any],
    guard: ShareCountHeadGuard,
    signer: ShareCountSigner,
) -> tuple[dict[str, Any] | None, str | None]:
    """Finish a durable ``cas_started`` intent with at most two fresh CASes.

    A process can die after persisting the intent but before entering
    ``guard.advance``.  The intent and immutable candidate are already sealed,
    so retrying the *same* conditional transition is safe: either it wins, an
    in-flight original request won, or a distinct selected head has made the
    original expectation stale.  Two attempts absorb a benign token churn
    without turning recovery into an unbounded contention loop.
    """
    for attempt in range(2):
        head, token = _read_authenticated_head(
            lane,
            guard=guard,
            signer=signer,
            label=f"pending CAS recovery head read {attempt + 1}",
        )
        if head != expected:
            return head, token
        lane.assert_bound(label="before pending CAS recovery transition")
        lane.operation.check("pending CAS recovery transition")
        invoked = False
        try:
            owner = getattr(guard.advance, "__self__", None)
            bind_deadline = getattr(owner, "_bind_deadline", None)
            deadline_context = (
                bind_deadline(lane.operation)
                if callable(bind_deadline)
                else contextlib.nullcontext()
            )
            with deadline_context:
                invoked = True
                guard.advance(
                    expected=expected,
                    expected_token=token,
                    candidate=candidate,
                )
            # A successful guard may be followed by a deadline/rebind failure;
            # retain the signed state in that case and let the next recovery
            # select the externally witnessed candidate.
            lane.assert_bound(
                label="after pending CAS recovery transition",
                check_deadline=False,
            )
            lane.operation.check("pending CAS recovery transition")
        except ShareCountPublicationConflict:
            # Fetch a new token/body and retry only once.  A new body is a
            # terminal external decision and is handled by the caller.
            continue
        except _ShareCountPreCasFailure as exc:
            # The concrete R2 guard proves no request was issued.  Keeping the
            # durable intent is safe and allows a later recovery to retry when
            # the transient read/deadline condition clears.
            raise ShareCountPublishIndeterminate(
                "share-count pending CAS recovery was not invoked",
            ) from exc
        except ShareCountPublishIndeterminate:
            raise
        except Exception as exc:  # noqa: BLE001 - invocation outcome is unknown
            if invoked:
                raise ShareCountPublishIndeterminate(
                    "share-count pending CAS recovery outcome is indeterminate",
                ) from exc
            raise
        return _read_authenticated_head(
            lane,
            guard=guard,
            signer=signer,
            label="pending CAS recovery confirmation",
        )
    head, token = _read_authenticated_head(
        lane,
        guard=guard,
        signer=signer,
        label="pending CAS recovery conflict confirmation",
    )
    if head == expected:
        raise ShareCountPublishIndeterminate(
            "share-count pending CAS recovery remains contested at expected head",
        )
    return head, token


def _clear_pending_recovery_records(
    lane: _PublicationLane,
    *,
    marker_body: bytes | None,
    capsule_body: bytes | None,
) -> None:
    """Remove exact records after their external outcome is already settled.

    The marker is removed first for compatibility with previously durable v2
    state.  A crash between the two unlinks leaves a signed capsule only; that
    state is deliberately recognized as an abandoned-or-committed pre-marker
    artifact by ``_recover_locked`` rather than becoming a terminal error.
    """
    if marker_body is not None:
        _remove_exact_at(
            lane.base_fd,
            PENDING_NAME,
            marker_body,
            max_bytes=MAX_PENDING_MARKER_BYTES,
            label="pending marker",
            operation=lane.operation,
        )
    if capsule_body is not None:
        _remove_exact_at(
            lane.base_fd,
            RECOVERY_NAME,
            capsule_body,
            max_bytes=MAX_RECOVERY_CAPSULE_BYTES,
            label="recovery capsule",
            operation=lane.operation,
        )


def _recover_publish_journal_locked(
    lane: _PublicationLane,
    *,
    journal: Mapping[str, Any],
    journal_body: bytes,
    signer: ShareCountSigner,
    guard: ShareCountHeadGuard,
    trace: _RecoveryTrace | None,
) -> ShareCountPublicationResult | None:
    """Converge one durable v1 journal without ever inventing a new intent."""
    journal = _validate_journal(journal, signer=signer)
    expected = journal["expected_witness"]
    candidate = journal["candidate_witness"]
    local = _read_local_selector(lane, signer=signer, witness=None)
    current_pointer = _local_pointer_body(lane)
    head, _ = _read_authenticated_head(
        lane,
        guard=guard,
        signer=signer,
        label="publish journal external head read",
    )
    if trace is not None:
        trace.selected_head = None if head is None else dict(head)

    virtual_head = head
    migrated_head = head is not None and head.get("schema") == WITNESS_V3_SCHEMA
    if migrated_head:
        virtual_head = _virtual_v2_witness_from_v3(
            head,
            signer=signer,
            expected_scope=guard.guard_scope,
        )
    _assert_local_high_water(local, head)

    candidate_receipt: dict[str, Any] | None = None
    candidate_receipt_body: bytes | None = None
    candidate_ledger: bytes | None = None
    if virtual_head == expected and not migrated_head:
        # A journal is commit intent, but not permission to select bytes that
        # disappeared after sealing.  Re-read and authenticate both immutable
        # candidate objects before the first recovery CAS.
        candidate_receipt, candidate_receipt_body = _read_selected_external_receipt(
            lane,
            candidate,
            guard=guard,
            signer=signer,
        )
        candidate_ledger = _read_selected_external_ledger(
            lane,
            candidate,
            receipt=candidate_receipt,
            receipt_body=candidate_receipt_body,
            guard=guard,
            signer=signer,
        )
        head, _ = _replay_cas_started_transition(
            lane,
            expected=expected,
            candidate=candidate,
            guard=guard,
            signer=signer,
        )
        if trace is not None:
            trace.selected_head = None if head is None else dict(head)
        virtual_head = head
        migrated_head = head is not None and head.get("schema") == WITNESS_V3_SCHEMA
        if migrated_head:
            virtual_head = _virtual_v2_witness_from_v3(
                head,
                signer=signer,
                expected_scope=guard.guard_scope,
            )

    if head is None or virtual_head is None:
        raise ShareCountPublishIndeterminate(
            "share-count publish journal external head remains unresolved",
        )

    # A scope-valid v3 migration of E wins over the pending v2 successor: the
    # old writer is fenced and recovery converges to E.  Every other accepted
    # head must be C or an authenticated descendant of E.  A direct sibling C'
    # is therefore a legitimate external winner, not a fork.
    selected_receipt: dict[str, Any]
    selected_receipt_body: bytes
    selected_ledger: bytes
    if virtual_head == candidate and candidate_receipt is not None:
        selected_receipt = candidate_receipt
        assert candidate_receipt_body is not None and candidate_ledger is not None
        selected_receipt_body = candidate_receipt_body
        selected_ledger = candidate_ledger
    else:
        selected_receipt, selected_receipt_body = _read_selected_external_receipt(
            lane,
            head,
            guard=guard,
            signer=signer,
        )
        if expected is not None:
            _prove_pending_expected_high_water(
                lane,
                expected=expected,
                head=virtual_head,
                head_receipt=selected_receipt,
                head_receipt_body=selected_receipt_body,
                guard=guard,
                signer=signer,
            )
        selected_ledger = _read_selected_external_ledger(
            lane,
            head,
            receipt=selected_receipt,
            receipt_body=selected_receipt_body,
            guard=guard,
            signer=signer,
        )
    if expected is not None and virtual_head == candidate:
        # Pin the exact predecessor even when the selected body is C.  This is
        # redundant with C's transition validation but makes the journal's
        # temporary high-water explicit and keeps the proof matrix uniform.
        _prove_pending_expected_high_water(
            lane,
            expected=expected,
            head=virtual_head,
            head_receipt=selected_receipt,
            head_receipt_body=selected_receipt_body,
            guard=guard,
            signer=signer,
        )
    _prove_local_high_water(
        lane,
        local=local,
        head=head,
        head_receipt=selected_receipt,
        head_receipt_body=selected_receipt_body,
        guard=guard,
        signer=signer,
    )

    if local is not None and _pointer_matches_witness(local.pointer, head):
        result = _load_local_result(lane, selection=local)
        if result.ledger_bytes != selected_ledger:
            raise ShareCountPublicationError(
                "share-count local ledger differs from journal-selected external bytes",
            )
    else:
        result = _install_external_bundle(
            lane,
            head=head,
            receipt=selected_receipt,
            receipt_body=selected_receipt_body,
            ledger=selected_ledger,
            expected_pointer=current_pointer,
        )
    lane.arm_terminal_cleanup(label="publish journal recovery completion")
    _clear_publish_journal(lane, journal_body)
    return result


def _recover_locked(
    lane: _PublicationLane,
    *,
    signer: ShareCountSigner,
    guard: ShareCountHeadGuard,
    trace: _RecoveryTrace | None = None,
) -> ShareCountPublicationResult | None:
    # All local intent names are observed before the first remote operation.
    # Mixed protocols are terminal ambiguity: exact bytes stay untouched and
    # even an authenticated remote selector cannot adjudicate which writer had
    # authority to proceed.
    journal_body_at_entry = _bounded_read_at(
        lane.base_fd,
        JOURNAL_NAME,
        max_bytes=MAX_PUBLISH_JOURNAL_BYTES,
        label="publish journal",
        operation=lane.operation,
        missing_ok=True,
    )
    marker_body_at_entry = _bounded_read_at(
        lane.base_fd,
        PENDING_NAME,
        max_bytes=MAX_PENDING_MARKER_BYTES,
        label="pending marker",
        operation=lane.operation,
        missing_ok=True,
    )
    capsule_body_at_entry = _bounded_read_at(
        lane.base_fd,
        RECOVERY_NAME,
        max_bytes=MAX_RECOVERY_CAPSULE_BYTES,
        label="recovery capsule",
        operation=lane.operation,
        missing_ok=True,
    )
    legacy_seen_at_entry = (
        marker_body_at_entry is not None or capsule_body_at_entry is not None
    )
    journal_seen_at_entry = journal_body_at_entry is not None
    if trace is not None:
        trace.legacy_seen_at_entry = legacy_seen_at_entry
        trace.journal_seen_at_entry = journal_seen_at_entry
        trace.recovery_seen_at_entry = legacy_seen_at_entry or journal_seen_at_entry
    if journal_seen_at_entry and legacy_seen_at_entry:
        raise ShareCountPublishIndeterminate(
            "share-count publish journal cannot coexist with legacy recovery records",
        )
    if journal_body_at_entry is not None:
        journal = _parse_canonical_json(
            journal_body_at_entry,
            label="publish journal",
            max_bytes=MAX_PUBLISH_JOURNAL_BYTES,
        )
        journal = _validate_journal(journal, signer=signer)
        lane.operation.check("publish journal validation")
        return _recover_publish_journal_locked(
            lane,
            journal=journal,
            journal_body=journal_body_at_entry,
            signer=signer,
            guard=guard,
            trace=trace,
        )
    head, _ = _read_authenticated_head(
        lane,
        guard=guard,
        signer=signer,
        label="external head read",
    )
    if trace is not None:
        trace.selected_head = None if head is None else dict(head)
    # Read and authenticate the retained selector before processing any marker
    # that could install external bytes.  This selector and its signed receipt
    # form the local high-water; a replayed signed head may not erase it.
    local = _read_local_selector(lane, signer=signer, witness=None)
    _assert_local_high_water(local, head)
    expected_pointer = None if local is None else _canonical_bytes(dict(local.pointer)) + b"\n"
    if (
        head is not None
        and head.get("schema") == WITNESS_V3_SCHEMA
        and legacy_seen_at_entry
    ):
        # Even malformed legacy bytes remain exact operator evidence.  A v3
        # downgrade fence and any v2 recovery artifact may never be reconciled
        # in one invocation.
        raise ShareCountPublishIndeterminate(
            "share-count v3 head cannot coexist with legacy recovery records",
        )
    marker_loaded = (
        None
        if marker_body_at_entry is None
        else _decode_signed_record(
            marker_body_at_entry,
            max_bytes=MAX_PENDING_MARKER_BYTES,
            label="pending marker",
            lane=lane,
        )
    )
    capsule_loaded = (
        None
        if capsule_body_at_entry is None
        else _decode_signed_record(
            capsule_body_at_entry,
            max_bytes=MAX_RECOVERY_CAPSULE_BYTES,
            label="recovery capsule",
            lane=lane,
        )
    )
    capsule_expected_high_water: Mapping[str, Any] | None = None
    capsule_required_high_water: Mapping[str, Any] | None = None
    orphan_capsule_body: bytes | None = None
    prepared_marker_body: bytes | None = None
    prepared_capsule_body: bytes | None = None
    if marker_loaded is not None:
        marker, marker_body = marker_loaded
        marker = _validate_marker(marker, signer=signer)
        lane.operation.check("pending marker validation")
        expected, candidate = marker["expected_witness"], marker["candidate_witness"]
        if capsule_loaded is None:
            raise ShareCountPublishIndeterminate("share-count pending marker has no recovery capsule")
        capsule, capsule_body = capsule_loaded
        _validate_capsule(capsule, signer=signer, expected=expected, candidate=candidate)
        lane.operation.check("recovery capsule validation")
        if _sha(capsule_body) != marker["recovery_sha256"] or len(capsule_body) != marker["recovery_byte_length"]:
            raise ShareCountPublishIndeterminate("share-count pending recovery capsule is detached")
        if head == expected and marker.get("phase") == "prepared":
            # A testable/process-visible failure before the committed "cas_started"
            # marker is provably pre-CAS.  Retain both exact signed records until
            # the selected ledger has also passed its delayed validation; losing
            # them first would erase the only restart evidence on ledger failure.
            prepared_marker_body = marker_body
            prepared_capsule_body = capsule_body
        elif head == expected:
            # ``cas_started`` is a durable commit intent, not evidence that a
            # network call happened.  A hard crash in the tiny window before
            # ``advance`` used to strand this exact state forever.  Re-drive
            # the same sealed transition with a fresh token; a competing
            # selected head makes the old expectation terminally stale.
            head, _ = _replay_cas_started_transition(
                lane,
                expected=expected,
                candidate=candidate,
                guard=guard,
                signer=signer,
            )
            if trace is not None:
                trace.selected_head = None if head is None else dict(head)
            if head == expected:
                raise ShareCountPublishIndeterminate(
                    "share-count pending CAS recovery did not advance expected head",
                )
        if head is not None and head != expected:
            # A distinct authenticated successor makes this candidate's CAS
            # token permanently stale.  It cannot land later, so converge to
            # the selected external head rather than pinning a losing writer.
            receipt, receipt_body = _read_selected_external_receipt(
                lane, head, guard=guard, signer=signer,
            )
            if expected is not None:
                _prove_pending_expected_high_water(
                    lane,
                    expected=expected,
                    head=head,
                    head_receipt=receipt,
                    head_receipt_body=receipt_body,
                    guard=guard,
                    signer=signer,
                )
            _prove_local_high_water(
                lane,
                local=local,
                head=head,
                head_receipt=receipt,
                head_receipt_body=receipt_body,
                guard=guard,
                signer=signer,
            )
            ledger = _read_selected_external_ledger(
                lane,
                head,
                receipt=receipt,
                receipt_body=receipt_body,
                guard=guard,
                signer=signer,
            )
            result = _install_external_bundle(
                lane,
                head=head,
                receipt=receipt,
                receipt_body=receipt_body,
                ledger=ledger,
                expected_pointer=expected_pointer,
            )
            _clear_pending_recovery_records(
                lane,
                marker_body=marker_body,
                capsule_body=capsule_body,
            )
            return result
        if head != expected:
            raise ShareCountPublishIndeterminate("share-count pending external head outcome is unresolved")
    elif capsule_loaded is not None:
        capsule, capsule_body = capsule_loaded
        # A capsule is durable *before* the marker and survives the legacy
        # marker-first final cleanup order.  It contains no authority to drive
        # a CAS by itself, so after authenticating its bounded pointer payloads
        # it may be reconciled only after its expected witness has protected
        # a missing local pointer from a forked external replacement.
        # In particular this makes both a crash before marker creation and a
        # crash after marker deletion recoverable rather than terminal.
        capsule = _validate_capsule(capsule, signer=signer)
        capsule_expected_high_water = capsule["expected_witness"]
        candidate = capsule["candidate_witness"]
        # Strict legacy matrix.  H==E is a provable pre-marker crash and may
        # clear after E's selected bundle validates.  H==C or a descendant of C
        # is the historical marker-first cleanup gap and must prove C as its
        # high-water.  Every sibling, equal-sequence fork, or rollback is
        # rejected while preserving the exact capsule and pointer bytes.
        if head == capsule_expected_high_water:
            capsule_required_high_water = capsule_expected_high_water
        elif head == candidate:
            capsule_required_high_water = candidate
        elif head is None:
            capsule_required_high_water = candidate
        elif head["sequence"] <= candidate["sequence"]:
            raise ShareCountPublicationError(
                "share-count orphan recovery capsule conflicts with the selected external head",
            )
        else:
            capsule_required_high_water = candidate
        orphan_capsule_body = capsule_body
        lane.operation.check("orphan recovery capsule validation")
    if head is None:
        if local is not None or capsule_expected_high_water is not None:
            raise ShareCountPublicationError(
                "share-count external head is below authenticated recovery high-water",
            )
        if prepared_marker_body is not None:
            _clear_pending_recovery_records(
                lane,
                marker_body=prepared_marker_body,
                capsule_body=prepared_capsule_body,
            )
        elif orphan_capsule_body is not None:
            _clear_pending_recovery_records(
                lane,
                marker_body=None,
                capsule_body=orphan_capsule_body,
            )
        lane.assert_bound(label="empty recovery completion")
        return None
    if local is not None and _pointer_matches_witness(local.pointer, head):
        if capsule_required_high_water is not None:
            _prove_pending_expected_high_water(
                lane,
                expected=capsule_required_high_water,
                head=head,
                head_receipt=local.receipt,
                head_receipt_body=local.receipt_body,
                guard=guard,
                signer=signer,
            )
        result = _load_local_result(lane, selection=local)
        if prepared_marker_body is not None:
            _clear_pending_recovery_records(
                lane,
                marker_body=prepared_marker_body,
                capsule_body=prepared_capsule_body,
            )
        elif orphan_capsule_body is not None:
            _clear_pending_recovery_records(
                lane,
                marker_body=None,
                capsule_body=orphan_capsule_body,
            )
        lane.assert_bound(label="local recovery completion")
        return result
    receipt, receipt_body = _read_selected_external_receipt(
        lane, head, guard=guard, signer=signer,
    )
    if capsule_required_high_water is not None:
        _prove_pending_expected_high_water(
            lane,
            expected=capsule_required_high_water,
            head=head,
            head_receipt=receipt,
            head_receipt_body=receipt_body,
            guard=guard,
            signer=signer,
        )
    _prove_local_high_water(
        lane,
        local=local,
        head=head,
        head_receipt=receipt,
        head_receipt_body=receipt_body,
        guard=guard,
        signer=signer,
    )
    ledger = _read_selected_external_ledger(
        lane,
        head,
        receipt=receipt,
        receipt_body=receipt_body,
        guard=guard,
        signer=signer,
    )
    # A clean workspace intentionally has no global rollback memory.  It can
    # authenticate the selected receipt and ledger but cannot detect a
    # credential-level restore of the single mutable external head.
    result = _install_external_bundle(
        lane,
        head=head,
        receipt=receipt,
        receipt_body=receipt_body,
        ledger=ledger,
        expected_pointer=expected_pointer,
    )
    if prepared_marker_body is not None:
        _clear_pending_recovery_records(
            lane,
            marker_body=prepared_marker_body,
            capsule_body=prepared_capsule_body,
        )
    elif orphan_capsule_body is not None:
        _clear_pending_recovery_records(
            lane,
            marker_body=None,
            capsule_body=orphan_capsule_body,
        )
    return result


def _validate_r2_account_endpoint_binding(*, account_id: str, endpoint: str) -> None:
    if not _HEX32.fullmatch(account_id):
        raise ShareCountPublicationError(
            "SHARE_COUNT_HEAD_GUARD_ACCOUNT_ID must be exactly 32 lowercase hexadecimal characters",
        )
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise ShareCountPublicationError(
            "share-count head-guard R2 endpoint is invalid",
        ) from exc
    hostname = parsed.hostname
    allowed_hosts = {
        f"{account_id}.r2.cloudflarestorage.com",
        f"{account_id}.eu.r2.cloudflarestorage.com",
        f"{account_id}.fedramp.r2.cloudflarestorage.com",
    }
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path != ""
        or parsed.query != ""
        or parsed.fragment != ""
        or hostname not in allowed_hosts
        or parsed.netloc != hostname
    ):
        raise ShareCountPublicationError(
            "share-count head-guard account does not match the exact Cloudflare R2 endpoint",
        )


def _production_trust(
    *,
    migration_enabled: bool = False,
) -> tuple[ShareCountSigner, ShareCountHeadGuard]:
    secret = os.environ.get("CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_HMAC_KEY", "")
    key_id = (
        os.environ.get("SHARE_COUNT_HEAD_GUARD_KEY_ID")
        or os.environ.get("CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_KEY_ID")
        or "share-count-head-v2"
    )
    bucket = os.environ.get("SHARE_COUNT_HEAD_GUARD_BUCKET") or os.environ.get("R2_CAPITAL_STRUCTURE_BUCKET") or os.environ.get("R2_BUCKET")
    account_id = os.environ.get("SHARE_COUNT_HEAD_GUARD_ACCOUNT_ID", "")
    if not secret or not bucket:
        raise ShareCountPublicationError(
            "share-count production trust is unconfigured: require CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_HMAC_KEY and a head-guard R2 bucket",
        )
    if migration_enabled and not account_id:
        raise ShareCountPublicationError(
            "share-count v3 migration requires SHARE_COUNT_HEAD_GUARD_ACCOUNT_ID",
        )
    if account_id:
        endpoint = (
            os.environ.get("R2_CAPITAL_STRUCTURE_ENDPOINT")
            or os.environ.get("R2_ENDPOINT")
            or ""
        )
        if not endpoint:
            raise ShareCountPublicationError(
                "share-count v3 head guard requires an explicit Cloudflare R2 endpoint",
            )
        _validate_r2_account_endpoint_binding(
            account_id=account_id,
            endpoint=endpoint,
        )
    try:
        from engine.capital_structure.source_store import _capital_structure_r2_client
        client = _capital_structure_r2_client()
        if client is None:
            raise ShareCountPublicationError("share-count external head R2 client is unavailable")
        signer = HmacShareCountSigner(secret, key_id=key_id)
        return signer, R2ShareCountHeadGuard(
            client=client,
            bucket=bucket,
            signer=signer,
            account_id=account_id or None,
        )
    except ShareCountPublicationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ShareCountPublicationError("share-count production trust is unconfigured") from exc


def _is_not_found_error(error: Exception) -> bool:
    response = getattr(error, "response", None)
    details = response.get("Error") if isinstance(response, Mapping) else None
    return isinstance(details, Mapping) and str(details.get("Code") or "") in {"404", "NoSuchKey", "NotFound"}


def _is_conditional_write_conflict(error: Exception) -> bool:
    response = getattr(error, "response", None)
    details = response.get("Error") if isinstance(response, Mapping) else None
    metadata = response.get("ResponseMetadata") if isinstance(response, Mapping) else None
    code = str(details.get("Code") or "") if isinstance(details, Mapping) else ""
    status = metadata.get("HTTPStatusCode") if isinstance(metadata, Mapping) else None
    return code in {"409", "412", "ConditionalRequestConflict", "PreconditionFailed"} or status in {409, 412}


def _require_deadline(deadline: float, monotonic: Callable[[], float], *, label: str) -> None:
    if monotonic() >= deadline:
        raise ShareCountPublicationError(f"share-count publication deadline exceeded during {label}")


def _operation_budget(max_operation_seconds: float | None) -> float:
    if max_operation_seconds is None:
        return PUBLICATION_TIMEOUT_SECONDS
    if isinstance(max_operation_seconds, bool):
        raise ShareCountPublicationError("share-count publication operation budget must be positive")
    try:
        seconds = float(max_operation_seconds)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ShareCountPublicationError(
            "share-count publication operation budget must be positive",
        ) from exc
    if not math.isfinite(seconds) or seconds <= 0:
        raise ShareCountPublicationError("share-count publication operation budget must be positive")
    return min(seconds, PUBLICATION_TIMEOUT_SECONDS)


def _head_v3_migration_enabled() -> bool:
    raw = os.environ.get(
        "CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_V3_MIGRATION_ENABLED",
        "false",
    )
    if raw not in {"true", "false"}:
        raise ShareCountPublicationError(
            "CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_V3_MIGRATION_ENABLED must be exactly true or false",
        )
    return raw == "true"


def _validate_production_ledger(ledger_bytes: bytes, input_binding: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    ledger = _parse_canonical_json(ledger_bytes, label="candidate ledger", max_bytes=MAX_LEDGER_BYTES)
    try:
        from engine.capital_structure.share_count_materializer import validate_share_count_ledger
        validate_share_count_ledger(ledger)
    except ShareCountPublicationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ShareCountPublicationError("share-count candidate ledger fails materializer validation") from exc
    return ledger, _validate_input_binding(input_binding, ledger)


def _fault(fault: Callable[[str], None] | None, stage: str) -> None:
    if fault is not None:
        fault(stage)


def _sign_receipt(record: Mapping[str, Any], *, signer: ShareCountSigner) -> dict[str, Any]:
    signed = dict(record)
    signed["receipt_id"] = _receipt_id(signed)
    signed["auth"] = {"scheme": AUTH_SCHEME, "key_id": signer.key_id, "signature": signer.sign(_receipt_auth_payload(signed))}
    _validate_receipt(signed, signer=signer)
    return signed


def _require_sequence_capacity(expected_head: Mapping[str, Any] | None) -> None:
    if expected_head is not None and int(expected_head["sequence"]) >= MAX_RECEIPT_SEQUENCE:
        raise ShareCountPublicationTooLarge(
            "share-count receipt sequence exceeds the v2 binary-lifting bound",
        )


def _publish_share_count_materialization_for_test(
    *, root: Path, canonical_ledger_bytes: bytes, input_binding: Mapping[str, Any],
    signer: ShareCountSigner, head_guard: ShareCountHeadGuard, now: datetime | None = None,
    fault: Callable[[str], None] | None = None, validate_ledger: bool = True,
    migrate_head_v3: bool = False,
    deadline: float | None = None, monotonic: Callable[[], float] = time.monotonic,
) -> ShareCountPublicationResult:
    """Injected test seam; production callers must use the public entry point."""
    start_deadline = deadline if deadline is not None else monotonic() + LEASE_TIMEOUT_SECONDS
    _require_deadline(start_deadline, monotonic, label="trust and lease acquisition")
    with _publication_lease(root, deadline=start_deadline, monotonic=monotonic) as lane:
        lane.operation.check("recovery")
        trace = _RecoveryTrace()
        current = _recover_locked(
            lane,
            signer=signer,
            guard=head_guard,
            trace=trace,
        )
        if trace.recovery_seen_at_entry:
            # An invocation that entered with any durable recovery evidence is
            # recovery-only.  Even successfully cleared evidence may not be
            # followed by migration or by validation of a fresh candidate.
            if current is not None:
                lane.assert_bound(label="recovery-only publication completion")
                return current
            raise ShareCountPublishIndeterminate(
                "share-count recovery-only invocation selected no head; retry from a second clean invocation",
            )
        if (
            not isinstance(canonical_ledger_bytes, bytes)
            or not 1 <= len(canonical_ledger_bytes) <= MAX_LEDGER_BYTES
        ):
            raise ShareCountPublicationTooLarge(
                "share-count candidate ledger exceeds byte cap",
            )
        active_head = _maybe_migrate_head_v3(
            lane,
            current=current,
            trace=trace,
            guard=head_guard,
            signer=signer,
            enabled=migrate_head_v3,
        )
        lane.operation.check("candidate validation")
        candidate_ledger = _parse_canonical_json(canonical_ledger_bytes, label="candidate ledger", max_bytes=MAX_LEDGER_BYTES)
        if validate_ledger:
            try:
                from engine.capital_structure.share_count_materializer import validate_share_count_ledger
                validate_share_count_ledger(candidate_ledger)
            except Exception as exc:  # noqa: BLE001
                raise ShareCountPublicationError("share-count candidate ledger fails materializer validation") from exc
            binding = _validate_input_binding(input_binding, candidate_ledger)
        else:
            # Even test fixtures retain the closed constant-size binding shape,
            # so receipt/head tests exercise real tail commitments.
            binding = _validate_binding_shape(input_binding)
        lane.operation.check("candidate validation")
        if current is not None and (
            current.receipt["generation"]["ledger_sha256"] == _sha(canonical_ledger_bytes)
            and current.receipt["generation"]["ledger_byte_length"] == len(canonical_ledger_bytes)
            and current.receipt["input_binding"] == binding
        ):
            lane.assert_bound(label="no-op publication completion")
            return current
        expected_head, expected_token = _read_authenticated_head(
            lane,
            guard=head_guard,
            signer=signer,
            label="pre-publication external head read",
        )
        if expected_head is not None and expected_head.get("schema") == WITNESS_V3_SCHEMA:
            raise ShareCountPublicationError(
                "share-count v3 external head is a migration fence; new publication is disabled",
            )
        if migrate_head_v3:
            if trace.legacy_seen_at_entry:
                raise ShareCountPublicationError(
                    "share-count v3 migration is deferred after legacy recovery",
                )
            if active_head is None:
                raise ShareCountPublicationError(
                    "share-count v3 migration mode cannot create a genesis publication",
                )
            raise ShareCountPublicationError(
                "share-count v3 migration mode cannot publish a successor",
            )
        if (current is None) != (expected_head is None):
            raise ShareCountPublicationError("share-count local and external selector disagree before publish")
        if current is not None and not _pointer_matches_witness(current.pointer, expected_head):
            raise ShareCountPublicationError("share-count current selector changed before publish")
        _assert_local_high_water(current, expected_head)
        _require_sequence_capacity(expected_head)
        lane.operation.check("receipt sequence capacity preflight")
        _stage_ledger(lane, canonical_ledger_bytes)
        digest = _sha(canonical_ledger_bytes)
        generation = {"generation_id": _generation_id(digest), "ledger_sha256": digest, "ledger_byte_length": len(canonical_ledger_bytes)}
        sequence = 1 if expected_head is None else expected_head["sequence"] + 1
        current_receipt_body = (
            None if current is None else _canonical_bytes(dict(current.receipt)) + b"\n"
        )
        previous = (
            None
            if current is None or current_receipt_body is None
            else _receipt_ref(current.receipt, current_receipt_body)
        )
        ancestor_refs = (
            []
            if current is None or current_receipt_body is None
            else _build_ancestor_refs(
                lane,
                predecessor=current.receipt,
                predecessor_body=current_receipt_body,
                candidate_sequence=sequence,
                guard=head_guard,
                signer=signer,
            )
        )
        timestamp = now or datetime.now(timezone.utc)
        if expected_head is not None:
            timestamp = max(timestamp.astimezone(timezone.utc), _stamp(expected_head["published_at"], label="prior head timestamp"))
        unsigned: dict[str, Any] = {
            "schema": RECEIPT_SCHEMA, "receipt_id": "", "sequence": sequence,
            "previous_receipt": previous, "ancestor_refs": ancestor_refs,
            "published_at": _iso(timestamp), "generation": generation,
            "input_binding": binding, "output_authority": _output_authority(),
            "auth": {"scheme": AUTH_SCHEME, "key_id": signer.key_id, "signature": ""},
        }
        receipt = _sign_receipt(unsigned, signer=signer)
        receipt_body = _canonical_bytes(receipt) + b"\n"
        witness = _head_witness(receipt=receipt, receipt_body=receipt_body, signer=signer)
        pointer = _pointer_for(receipt=receipt, receipt_body=receipt_body)
        pointer_body = _canonical_bytes(pointer) + b"\n"
        lane.operation.check("publication record construction")
        expected_pointer = _local_pointer_body(lane)
        # Immutable local and external artifacts are all exact-read before the
        # sole externally authoritative transition.  External objects let a
        # later clean workspace recover even if local staging is swept.
        generation_name = _id_digest(
            generation["generation_id"], prefix=_GENERATION_PREFIX, label="generation",
        )
        with lane.directory(
            lane.generations_fd,
            generation_name,
            create=True,
            label="generation",
        ) as generation_fd:
            _write_immutable_at(
                generation_fd,
                "ledger.json",
                canonical_ledger_bytes,
                max_bytes=MAX_LEDGER_BYTES,
                label="generation ledger",
                operation=lane.operation,
            )
        receipt_name = _id_digest(
            receipt["receipt_id"], prefix=_RECEIPT_PREFIX, label="materialization receipt",
        ) + ".json"
        _write_immutable_at(
            lane.receipts_fd,
            receipt_name,
            receipt_body,
            max_bytes=MAX_RECEIPT_BYTES,
            label="materialization receipt",
            operation=lane.operation,
        )
        _guard_call(
            lane,
            label="external immutable ledger seal",
            call=head_guard.seal_artifact,
            kwargs={
                "key": witness["ledger_object_key"],
                "body": canonical_ledger_bytes,
                "max_bytes": MAX_LEDGER_BYTES,
            },
        )
        _guard_call(
            lane,
            label="external immutable receipt seal",
            call=head_guard.seal_artifact,
            kwargs={
                "key": witness["receipt_object_key"],
                "body": receipt_body,
                "max_bytes": MAX_RECEIPT_BYTES,
            },
        )
        # Explicit exact re-reads close the gap between an idempotent seal and
        # durable commit intent.  A journal may never name bytes that were not
        # independently observed in the external immutable store.
        sealed_ledger = _guard_call(
            lane,
            label="external immutable ledger exact read-back",
            call=head_guard.read_artifact,
            kwargs={
                "key": witness["ledger_object_key"],
                "max_bytes": MAX_LEDGER_BYTES,
            },
        )
        sealed_receipt = _guard_call(
            lane,
            label="external immutable receipt exact read-back",
            call=head_guard.read_artifact,
            kwargs={
                "key": witness["receipt_object_key"],
                "max_bytes": MAX_RECEIPT_BYTES,
            },
        )
        if sealed_ledger != canonical_ledger_bytes or sealed_receipt != receipt_body:
            raise ShareCountPublicationError(
                "share-count external immutable artifact exact read-back mismatch",
            )
        lane.assert_bound(label="publish journal preflight")
        journal = _journal(
            expected=expected_head,
            candidate=witness,
            expected_pointer=expected_pointer,
            candidate_pointer=pointer_body,
            signer=signer,
        )
        lane.operation.check("publish journal construction")
        journal_body = _write_publish_journal(lane, journal)
        lane.operation.check("before-CAS fault hook")
        _fault(fault, "before_cas")
        lane.operation.check("before-CAS fault hook")
        # The single journal is already durable commit intent.  From here every
        # failure preserves its exact bytes for deterministic recovery.
        lane.assert_bound(label="before external head CAS")
        lane.operation.check("external head commit")
        invoked = False
        advanced = False
        try:
            owner = getattr(head_guard.advance, "__self__", None)
            bind_deadline = getattr(owner, "_bind_deadline", None)
            deadline_context = (
                bind_deadline(lane.operation)
                if callable(bind_deadline)
                else contextlib.nullcontext()
            )
            with deadline_context:
                invoked = True
                head_guard.advance(
                    expected=expected_head,
                    expected_token=expected_token,
                    candidate=witness,
                )
                advanced = True
            lane.assert_bound(label="after external head CAS", check_deadline=False)
            lane.operation.check("external head commit")
        except (ShareCountPublicationConflict, _ShareCountPreCasFailure):
            raise
        except ShareCountPublishIndeterminate as exc:
            try:
                lane.assert_bound(
                    label="after indeterminate external head CAS",
                    check_deadline=False,
                )
            except ShareCountPublicationError as binding_exc:
                raise ShareCountPublishIndeterminate(
                    "share-count external head CAS is indeterminate and the publication lane was rebound",
                ) from binding_exc
            raise
        except Exception as exc:
            if advanced:
                raise ShareCountPublishIndeterminate(
                    "share-count external head committed after publication deadline or lane rebind",
                ) from exc
            if not invoked:
                raise
            with contextlib.suppress(ShareCountPublicationError):
                lane.assert_bound(
                    label="after failed external head CAS",
                    check_deadline=False,
                )
            raise ShareCountPublishIndeterminate(
                "share-count external head CAS outcome is indeterminate; publish journal retained",
            ) from exc
        try:
            lane.operation.check("after-CAS fault hook")
            _fault(fault, "after_cas")
            lane.operation.check("after-CAS fault hook")
            lane.assert_bound(label="local pointer commit")
            _atomic_write_at(
                lane.base_fd,
                POINTER_NAME,
                pointer_body,
                expected_previous=expected_pointer,
                max_bytes=MAX_POINTER_BYTES,
                label="current pointer",
                operation=lane.operation,
            )
            confirmed_selector = _read_local_selector(
                lane,
                signer=signer,
                witness=witness,
            )
            if confirmed_selector is None:
                raise ShareCountPublicationError("share-count local pointer disappeared after commit")
            confirmed = _load_local_result(
                lane,
                selection=confirmed_selector,
                published=True,
            )
            lane.arm_terminal_cleanup(label="publication completion")
            _clear_publish_journal(lane, journal_body)
            # Return the already-built result.  Journal cleanup is the final
            # fallible protocol operation; allocating a duplicate result after
            # the unlink could otherwise fail after exact recovery evidence is
            # gone.
            return confirmed
        except BaseException as exc:  # noqa: BLE001 - durable intent must restart through recovery
            if isinstance(exc, ShareCountPublishIndeterminate):
                raise
            raise ShareCountPublishIndeterminate(
                "share-count publication failed after durable intent; publish journal retained",
            ) from exc


def _recover_share_count_materialization_for_test(
    *, root: Path, signer: ShareCountSigner, head_guard: ShareCountHeadGuard,
    migrate_head_v3: bool = False,
    deadline: float | None = None, monotonic: Callable[[], float] = time.monotonic,
) -> ShareCountPublicationResult | None:
    start_deadline = deadline if deadline is not None else monotonic() + LEASE_TIMEOUT_SECONDS
    _require_deadline(start_deadline, monotonic, label="trust and lease acquisition")
    with _publication_lease(root, deadline=start_deadline, monotonic=monotonic) as lane:
        lane.operation.check("recovery")
        trace = _RecoveryTrace()
        result = _recover_locked(
            lane,
            signer=signer,
            guard=head_guard,
            trace=trace,
        )
        _maybe_migrate_head_v3(
            lane,
            current=result,
            trace=trace,
            guard=head_guard,
            signer=signer,
            enabled=migrate_head_v3,
        )
        lane.operation.check("recovery completion")
        lane.assert_bound(label="recovery completion")
        return result


def _publish_share_count_materialization_with_production_trust(
    *,
    canonical_ledger_bytes: bytes,
    input_binding: Mapping[str, Any],
    max_operation_seconds: float | None = None,
) -> ShareCountPublicationResult:
    """Private signing seam used only by the closed no-argument orchestrator.

    Production intentionally exposes no generic ``bytes -> signed head`` API.
    The command orchestrator authenticates the upstream head, strict-reads the
    retained raw suffix, and runs the pure compiler before it can call here.
    """
    monotonic = time.monotonic
    deadline = monotonic() + _operation_budget(max_operation_seconds)
    migrate_head_v3 = _head_v3_migration_enabled()
    signer, guard = _production_trust(migration_enabled=migrate_head_v3)
    _require_deadline(deadline, monotonic, label="production trust")
    # The storage boundary validates the candidate after recovery.  Do not
    # pre-validate here: an invocation that enters with durable recovery state
    # must remain recovery-only even when the caller supplied unusable bytes.
    return _publish_share_count_materialization_for_test(
        root=_storage_root(), canonical_ledger_bytes=canonical_ledger_bytes, input_binding=input_binding,
        signer=signer, head_guard=guard, now=datetime.now(timezone.utc), deadline=deadline,
        monotonic=monotonic, migrate_head_v3=migrate_head_v3,
    )


def recover_share_count_materialization(
    *, max_operation_seconds: float | None = None,
) -> ShareCountPublicationResult | None:
    """Restore a selected generation from the external signed head when needed."""
    monotonic = time.monotonic
    deadline = monotonic() + _operation_budget(max_operation_seconds)
    migrate_head_v3 = _head_v3_migration_enabled()
    signer, guard = _production_trust(migration_enabled=migrate_head_v3)
    _require_deadline(deadline, monotonic, label="production trust")
    return _recover_share_count_materialization_for_test(
        root=_storage_root(), signer=signer, head_guard=guard, deadline=deadline,
        monotonic=monotonic, migrate_head_v3=migrate_head_v3,
    )


__all__ = [
    "HmacShareCountSigner", "InMemoryShareCountHeadGuard", "MAX_ANCESTOR_REFS", "MAX_HEAD_WITNESS_BYTES",
    "MAX_LEDGER_BYTES", "MAX_POINTER_BYTES", "MAX_RECEIPT_BYTES", "R2ShareCountHeadGuard",
    "ShareCountHeadGuard", "ShareCountPublicationConflict", "ShareCountPublicationError",
    "ShareCountPublicationResult", "ShareCountPublicationTooLarge", "ShareCountPublishIndeterminate",
    "ShareCountSigner", "recover_share_count_materialization",
]
