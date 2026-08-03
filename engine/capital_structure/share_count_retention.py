"""Fail-closed, pre-production retention for share-count v2 ledger objects.

This module deliberately owns neither the publication head nor its signature
format.  ``AuthenticatedShareCountReader`` is a narrow, injected boundary: a
production implementation must authenticate the current signed head *and* its
selected receipt before returning, then authenticate the exact predecessor
receipt on request.  Until the publisher v2 public adapter is frozen, no
production implementation is wired here.  Retention therefore cannot turn a
moving publication implementation into a second authority.

Only immutable generation ``ledger.json`` objects in the exact v2 namespace can
be considered. Receipts are deliberately never listed for deletion. The pure
planner accepts an injected conditionally safe store for testing and future
adapters, but the R2 adapter intentionally refuses deletion until a live
provider conformance proof, a shared publisher/retention fence, and a capability
boundary that cannot write the signed head have all landed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import json
import math
import re
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence


V2_HEAD_OBJECT_KEY = "capital_structure/share_counts/v2/current_head.json"
V2_RECEIPT_OBJECT_PREFIX = "capital_structure/share_counts/v2/receipts/"
V2_GENERATION_OBJECT_PREFIX = "capital_structure/share_counts/v2/generations/"
V2_HEAD_SCHEMA = "capital_structure.share_count_head_witness/v2"
V2_RECEIPT_SCHEMA = "capital_structure.share_count_materialization_receipt/v2"
V2_RECEIPT_ID_PREFIX = "receipt:cs-share-count-materialization-v2:"
V2_GENERATION_ID_PREFIX = "generation:cs-share-count-materialization-v2:"

# The publication and recovery lanes have a 15 minute operational budget.  A
# three-day quarantine gives a deliberately large margin while bounding cost.
MIN_QUARANTINE_SECONDS = 48 * 60 * 60
DEFAULT_QUARANTINE_SECONDS = 72 * 60 * 60
DEFAULT_MAX_PAGES = 16
DEFAULT_MAX_OBJECTS = 4_096
DEFAULT_PAGE_SIZE = 256
MAX_RETENTION_RECEIPT_BYTES = 512 * 1024
RETENTION_RECEIPT_SCHEMA = "capital_structure.share_count_retention_receipt/v1"
RETENTION_AUTH_SCHEME = "hmac-sha256/v1"
RETENTION_R2_ENDPOINT_ENV = "CAPITAL_STRUCTURE_SHARE_COUNT_RETENTION_R2_ENDPOINT"
RETENTION_R2_ACCESS_KEY_ID_ENV = "CAPITAL_STRUCTURE_SHARE_COUNT_RETENTION_R2_ACCESS_KEY_ID"
RETENTION_R2_SECRET_ACCESS_KEY_ENV = "CAPITAL_STRUCTURE_SHARE_COUNT_RETENTION_R2_SECRET_ACCESS_KEY"
RETENTION_R2_BUCKET_ENV = "CAPITAL_STRUCTURE_SHARE_COUNT_RETENTION_R2_BUCKET"
RETENTION_R2_ENV_NAMES = (
    RETENTION_R2_ENDPOINT_ENV, RETENTION_R2_ACCESS_KEY_ID_ENV,
    RETENTION_R2_SECRET_ACCESS_KEY_ENV, RETENTION_R2_BUCKET_ENV,
)

_HEX64 = re.compile(r"^[a-f0-9]{64}$")
_LEDGER_KEY = re.compile(
    r"^capital_structure/share_counts/v2/generations/([a-f0-9]{64})/ledger\.json$",
)


class ShareCountRetentionError(RuntimeError):
    """The compactor cannot prove a bounded safe retention action."""


class ShareCountRetentionHeadChanged(ShareCountRetentionError):
    """The signed head changed after planning; a fresh plan is required."""


class ShareCountRetentionDeleteAmbiguity(ShareCountRetentionError):
    """A delete result was not a single unambiguous conditional success."""


@dataclass(frozen=True)
class AuthenticatedCurrentSelection:
    """A reader-authenticated signed head and the exact selected receipt."""

    head: Mapping[str, Any]
    head_token: str
    receipt: Mapping[str, Any]
    authenticated: bool = True


@dataclass(frozen=True)
class AuthenticatedReceipt:
    """An exact predecessor receipt authenticated by the reader boundary."""

    receipt: Mapping[str, Any]
    receipt_sha256: str
    receipt_byte_length: int
    authenticated: bool = True


class AuthenticatedShareCountReader(Protocol):
    """Closed authentication boundary supplied by the final publisher-v2 adapter."""

    def read_authenticated_current(self) -> AuthenticatedCurrentSelection: ...

    def read_authenticated_predecessor(
        self, current: AuthenticatedCurrentSelection,
    ) -> AuthenticatedReceipt: ...


class PublicationReadBoundary(Protocol):
    """Authenticated read-only surface owned by publication protocol v2."""

    def read_current(self) -> Any: ...

    def read_receipt(self, reference: Mapping[str, Any]) -> Any: ...


class PublisherV2RetentionReader:
    """Map the publisher's authenticated read proof into the retention protocol."""

    def __init__(self, *, publication_reader: PublicationReadBoundary) -> None:
        self._publication_reader = publication_reader

    def read_authenticated_current(self) -> AuthenticatedCurrentSelection:
        try:
            selected = self._publication_reader.read_current()
        except ShareCountRetentionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ShareCountRetentionError(
                "current share-count publication state cannot be authenticated",
            ) from exc
        return AuthenticatedCurrentSelection(
            head=selected.head,
            head_token=selected.head_token,
            receipt=selected.receipt,
            authenticated=True,
        )

    def read_authenticated_predecessor(
        self,
        current: AuthenticatedCurrentSelection,
    ) -> AuthenticatedReceipt:
        previous = current.receipt.get("previous_receipt")
        if not isinstance(previous, Mapping):
            raise ShareCountRetentionError(
                "current publication receipt has no predecessor to authenticate",
            )
        try:
            selected = self._publication_reader.read_receipt(previous)
        except ShareCountRetentionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ShareCountRetentionError(
                "share-count predecessor publication receipt cannot be authenticated",
            ) from exc
        return AuthenticatedReceipt(
            receipt=selected.receipt,
            receipt_sha256=selected.receipt_sha256,
            receipt_byte_length=selected.receipt_byte_length,
            authenticated=True,
        )


@dataclass(frozen=True)
class RetentionObject:
    key: str
    last_modified: datetime
    etag: str


@dataclass(frozen=True)
class RetentionListPage:
    objects: tuple[RetentionObject, ...]
    next_token: str | None


@dataclass(frozen=True)
class ConditionalDeleteResult:
    deleted: bool
    condition_matched: bool


class RetentionObjectStore(Protocol):
    """Dedicated-delete-store interface; delete must be conditionally safe."""

    def list_generation_ledgers(
        self, *, prefix: str, continuation_token: str | None, max_keys: int,
    ) -> RetentionListPage: ...

    def head_generation_ledger(self, *, key: str) -> RetentionObject: ...

    def delete_generation_ledger_if_unchanged(
        self, *, key: str, expected_etag: str, expected_last_modified: datetime,
    ) -> ConditionalDeleteResult: ...


class R2RetentionObjectStore:
    """Dedicated R2 object-store adapter with no generic/delete fallback path."""

    def __init__(self, *, client: Any, bucket: str) -> None:
        if client is None or not isinstance(bucket, str) or not bucket.strip():
            raise ValueError("dedicated share-count retention R2 client and bucket are required")
        self._client, self._bucket = client, bucket.strip()

    def list_generation_ledgers(
        self, *, prefix: str, continuation_token: str | None, max_keys: int,
    ) -> RetentionListPage:
        if prefix != V2_GENERATION_OBJECT_PREFIX or not isinstance(max_keys, int) or isinstance(max_keys, bool) or max_keys < 1:
            raise ShareCountRetentionError("retention R2 listing request is unsafe")
        arguments: dict[str, Any] = {"Bucket": self._bucket, "Prefix": prefix, "MaxKeys": max_keys}
        if continuation_token is not None:
            if not isinstance(continuation_token, str) or not continuation_token:
                raise ShareCountRetentionError("retention R2 continuation token is unsafe")
            arguments["ContinuationToken"] = continuation_token
        try:
            response = self._client.list_objects_v2(**arguments)
        except Exception as exc:  # noqa: BLE001
            raise ShareCountRetentionError("dedicated retention R2 listing failed") from exc
        _require_r2_status(response, allowed={200}, label="retention R2 listing")
        if not isinstance(response, Mapping) or response.get("IsTruncated") not in {True, False}:
            raise ShareCountRetentionError("retention R2 listing is malformed")
        contents = response.get("Contents", [])
        if not isinstance(contents, list) or len(contents) > max_keys:
            raise ShareCountRetentionError("retention R2 listing is malformed")
        key_count = response.get("KeyCount")
        if key_count is not None and (not isinstance(key_count, int) or isinstance(key_count, bool) or key_count != len(contents)):
            raise ShareCountRetentionError("retention R2 listing key count is malformed")
        objects = tuple(_r2_object(item, label="retention R2 listing") for item in contents)
        next_token = response.get("NextContinuationToken")
        if response["IsTruncated"]:
            if not isinstance(next_token, str) or not next_token:
                raise ShareCountRetentionError("retention R2 listing continuation is malformed")
        elif next_token is not None:
            raise ShareCountRetentionError("retention R2 listing has an unexpected continuation")
        return RetentionListPage(objects=objects, next_token=next_token)

    def head_generation_ledger(self, *, key: str) -> RetentionObject:
        _require_generation_ledger_key(key, label="retention R2 HEAD")
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=key)
        except Exception as exc:  # noqa: BLE001
            raise ShareCountRetentionError("dedicated retention R2 HEAD failed") from exc
        _require_r2_status(response, allowed={200}, label="retention R2 HEAD")
        if not isinstance(response, Mapping):
            raise ShareCountRetentionError("retention R2 HEAD is malformed")
        return _r2_object({"Key": key, "LastModified": response.get("LastModified"), "ETag": response.get("ETag")}, label="retention R2 HEAD")

    def delete_generation_ledger_if_unchanged(
        self, *, key: str, expected_etag: str, expected_last_modified: datetime,
    ) -> ConditionalDeleteResult:
        _require_generation_ledger_key(key, label="retention conditional delete")
        if not isinstance(expected_etag, str) or not expected_etag:
            raise ShareCountRetentionDeleteAmbiguity("retention conditional delete ETag is malformed")
        _aware(expected_last_modified, "retention conditional delete LastModified")
        raise ShareCountRetentionDeleteAmbiguity(
            "R2 conditional DeleteObject is not release-proven; production deletion is disabled",
        )


def build_dedicated_r2_retention_store(
    *, environ: Mapping[str, str], client_factory: Callable[..., Any] | None = None,
) -> R2RetentionObjectStore:
    """Build only from retention-named credentials; never fall back to publisher R2."""
    values = {name: environ.get(name, "").strip() for name in RETENTION_R2_ENV_NAMES}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ShareCountRetentionError(
            "dedicated retention R2 credentials are unconfigured: " + ", ".join(missing),
        )
    if client_factory is None:
        try:
            import boto3
            client_factory = boto3.client
        except Exception as exc:  # noqa: BLE001
            raise ShareCountRetentionError("boto3 is unavailable for dedicated retention R2") from exc
    try:
        client = client_factory(
            "s3", endpoint_url=values[RETENTION_R2_ENDPOINT_ENV],
            aws_access_key_id=values[RETENTION_R2_ACCESS_KEY_ID_ENV],
            aws_secret_access_key=values[RETENTION_R2_SECRET_ACCESS_KEY_ENV],
        )
    except Exception as exc:  # noqa: BLE001
        raise ShareCountRetentionError("dedicated retention R2 client is unavailable") from exc
    return R2RetentionObjectStore(client=client, bucket=values[RETENTION_R2_BUCKET_ENV])


@dataclass(frozen=True)
class RetentionPlan:
    head_token: str
    head_receipt_id: str
    protected_generation_keys: frozenset[str]
    candidate_objects: tuple[RetentionObject, ...]
    grace_objects: tuple[RetentionObject, ...]
    quarantine_seconds: int
    planned_at: datetime


@dataclass(frozen=True)
class RetentionRunResult:
    plan: RetentionPlan
    deleted_keys: tuple[str, ...]
    receipt: Mapping[str, Any]


class RetentionReceiptSigner(Protocol):
    @property
    def key_id(self) -> str: ...

    def sign(self, payload: bytes) -> str: ...

    def verify(self, payload: bytes, signature: str, *, key_id: str) -> bool: ...


class HmacRetentionReceiptSigner:
    """Domain-separated signer for non-authoritative retention audit receipts."""

    _DOMAIN = b"capital-structure-share-count-retention-receipt-v1\\0"

    def __init__(self, secret: str | bytes, *, key_id: str) -> None:
        raw = secret.encode("utf-8") if isinstance(secret, str) else secret
        if not isinstance(raw, bytes) or len(raw) < 32 or not isinstance(key_id, str) or not key_id:
            raise ValueError("retention receipt signer requires a 32-byte secret and key id")
        self._secret, self._key_id = raw, key_id

    @property
    def key_id(self) -> str:
        return self._key_id

    def sign(self, payload: bytes) -> str:
        return hmac.new(self._secret, self._DOMAIN + payload, sha256).hexdigest()

    def verify(self, payload: bytes, signature: str, *, key_id: str) -> bool:
        return key_id == self.key_id and isinstance(signature, str) and hmac.compare_digest(
            self.sign(payload), signature,
        )


def generation_ledger_key(generation_id: str) -> str:
    digest = _id_digest(generation_id, V2_GENERATION_ID_PREFIX, "generation")
    return f"{V2_GENERATION_OBJECT_PREFIX}{digest}/ledger.json"


def receipt_object_key(receipt_id: str) -> str:
    digest = _id_digest(receipt_id, V2_RECEIPT_ID_PREFIX, "receipt")
    return f"{V2_RECEIPT_OBJECT_PREFIX}{digest}.json"


def build_retention_plan(
    *, reader: AuthenticatedShareCountReader, store: RetentionObjectStore,
    now: datetime, quarantine_seconds: int = DEFAULT_QUARANTINE_SECONDS,
    max_pages: int = DEFAULT_MAX_PAGES, max_objects: int = DEFAULT_MAX_OBJECTS,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> RetentionPlan:
    """Authenticate first, then make one bounded deletion plan with no side effects."""
    now = _aware(now, "retention clock")
    _validate_limits(quarantine_seconds, max_pages, max_objects, page_size)
    current = _validated_current(reader.read_authenticated_current())
    protected = {generation_ledger_key(str(current.receipt["generation"]["generation_id"]))}
    previous = current.receipt.get("previous_receipt")
    if previous is not None:
        if not isinstance(previous, Mapping):
            raise ShareCountRetentionError("current receipt predecessor is malformed")
        predecessor = reader.read_authenticated_predecessor(current)
        if not isinstance(predecessor, AuthenticatedReceipt) or not predecessor.authenticated:
            raise ShareCountRetentionError("predecessor receipt authentication is missing")
        prior = _validate_receipt(predecessor.receipt, label="predecessor receipt")
        if (
            prior["receipt_id"] != previous.get("receipt_id")
            or predecessor.receipt_sha256 != previous.get("receipt_sha256")
            or predecessor.receipt_byte_length != previous.get("receipt_byte_length")
        ):
            raise ShareCountRetentionError("authenticated predecessor receipt is detached")
        protected.add(generation_ledger_key(str(prior["generation"]["generation_id"])))
    elif current.receipt["sequence"] != 1:
        raise ShareCountRetentionError("current receipt is missing its immediate predecessor")

    listed = _bounded_list(store=store, max_pages=max_pages, max_objects=max_objects, page_size=page_size)
    cutoff = now - timedelta(seconds=quarantine_seconds)
    candidates: list[RetentionObject] = []
    grace: list[RetentionObject] = []
    for item in listed:
        if item.key in protected:
            continue
        if item.last_modified > cutoff:
            grace.append(item)
        else:
            candidates.append(item)
    return RetentionPlan(
        head_token=current.head_token, head_receipt_id=str(current.receipt["receipt_id"]),
        protected_generation_keys=frozenset(protected), candidate_objects=tuple(candidates),
        grace_objects=tuple(grace), quarantine_seconds=quarantine_seconds, planned_at=now,
    )


def run_retention(
    *, reader: AuthenticatedShareCountReader, store: RetentionObjectStore,
    signer: RetentionReceiptSigner, now: datetime, apply: bool = False,
    quarantine_seconds: int = DEFAULT_QUARANTINE_SECONDS,
    max_pages: int = DEFAULT_MAX_PAGES, max_objects: int = DEFAULT_MAX_OBJECTS,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> RetentionRunResult:
    """Run dry by default; each apply-delete is re-guarded by the signed head."""
    plan = build_retention_plan(
        reader=reader, store=store, now=now, quarantine_seconds=quarantine_seconds,
        max_pages=max_pages, max_objects=max_objects, page_size=page_size,
    )
    deleted: list[str] = []
    if apply:
        cutoff = _aware(now, "retention clock") - timedelta(seconds=plan.quarantine_seconds)
        for candidate in plan.candidate_objects:
            _assert_stable_head(reader, plan)
            fresh = _validate_object(store.head_generation_ledger(key=candidate.key), label="deletion preflight")
            if fresh.key != candidate.key or fresh.etag != candidate.etag or fresh.last_modified != candidate.last_modified:
                raise ShareCountRetentionDeleteAmbiguity("generation ledger changed after retention planning")
            if fresh.key in plan.protected_generation_keys:
                raise ShareCountRetentionError("selected or protected generation is never deletable")
            if fresh.last_modified > cutoff:
                raise ShareCountRetentionError("generation ledger is still inside retention quarantine")
            outcome = store.delete_generation_ledger_if_unchanged(
                key=candidate.key, expected_etag=candidate.etag,
                expected_last_modified=candidate.last_modified,
            )
            if not isinstance(outcome, ConditionalDeleteResult) or not outcome.deleted or not outcome.condition_matched:
                raise ShareCountRetentionDeleteAmbiguity("conditional generation-ledger delete is ambiguous")
            deleted.append(candidate.key)
    receipt = _signed_receipt(plan=plan, deleted_keys=deleted, apply=apply, signer=signer)
    return RetentionRunResult(plan=plan, deleted_keys=tuple(deleted), receipt=receipt)


def write_retention_receipt(
    *, path: Path, receipt: Mapping[str, Any], signer: RetentionReceiptSigner,
) -> None:
    """Write a canonical audit receipt once; it is deliberately not a selector."""
    _validate_retention_receipt(receipt, signer=signer)
    body = _canonical_bytes(receipt) + b"\n"
    if len(body) > MAX_RETENTION_RECEIPT_BYTES:
        raise ShareCountRetentionError("retention receipt exceeds byte cap")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(body)
    except FileExistsError:
        if path.read_bytes() != body:
            raise ShareCountRetentionError("retention receipt identity already has different bytes")


def _assert_stable_head(reader: AuthenticatedShareCountReader, plan: RetentionPlan) -> None:
    current = _validated_current(reader.read_authenticated_current())
    if current.head_token != plan.head_token or current.receipt["receipt_id"] != plan.head_receipt_id:
        raise ShareCountRetentionHeadChanged("signed share-count head changed; retention must replan")


def _bounded_list(*, store: RetentionObjectStore, max_pages: int, max_objects: int, page_size: int) -> tuple[RetentionObject, ...]:
    token: str | None = None
    seen_tokens: set[str] = set()
    results: list[RetentionObject] = []
    seen_keys: set[str] = set()
    for _page in range(max_pages):
        page = store.list_generation_ledgers(
            prefix=V2_GENERATION_OBJECT_PREFIX, continuation_token=token, max_keys=page_size,
        )
        if not isinstance(page, RetentionListPage) or not isinstance(page.objects, tuple):
            raise ShareCountRetentionError("generation-ledger listing is malformed")
        for raw in page.objects:
            item = _validate_object(raw, label="generation-ledger listing")
            if item.key in seen_keys:
                raise ShareCountRetentionError("generation-ledger listing contains a duplicate key")
            seen_keys.add(item.key)
            results.append(item)
            if len(results) > max_objects:
                raise ShareCountRetentionError("generation-ledger listing exceeds object cap")
        if page.next_token is None:
            return tuple(results)
        if not isinstance(page.next_token, str) or not page.next_token or page.next_token in seen_tokens:
            raise ShareCountRetentionError("generation-ledger listing pagination is malformed")
        seen_tokens.add(page.next_token)
        token = page.next_token
    raise ShareCountRetentionError("generation-ledger listing exceeds page cap")


def _validated_current(value: Any) -> AuthenticatedCurrentSelection:
    if not isinstance(value, AuthenticatedCurrentSelection) or not value.authenticated:
        raise ShareCountRetentionError("current signed head/receipt authentication is missing")
    if not isinstance(value.head_token, str) or not value.head_token:
        raise ShareCountRetentionError("current signed head token is invalid")
    receipt = _validate_receipt(value.receipt, label="current receipt")
    head = value.head
    _validate_contract(head, "capital_structure_share_count_head_witness.schema.json", label="current signed head")
    if head.get("schema") != V2_HEAD_SCHEMA:
        raise ShareCountRetentionError("current signed head schema is malformed")
    if head.get("receipt_id") != receipt["receipt_id"] or head.get("receipt_object_key") != receipt_object_key(str(receipt["receipt_id"])):
        raise ShareCountRetentionError("current signed head is detached from current receipt")
    generation_id = receipt["generation"]["generation_id"]
    if head.get("generation_id") != generation_id or head.get("ledger_object_key") != generation_ledger_key(str(generation_id)):
        raise ShareCountRetentionError("current signed head is detached from selected ledger")
    if (
        head.get("ledger_sha256") != receipt["generation"].get("ledger_sha256")
        or head.get("ledger_byte_length") != receipt["generation"].get("ledger_byte_length")
    ):
        raise ShareCountRetentionError("current signed head ledger bytes are detached from current receipt")
    previous = receipt.get("previous_receipt")
    if head.get("previous_receipt") != previous:
        raise ShareCountRetentionError("current signed head predecessor is detached")
    if head.get("sequence") != receipt["sequence"]:
        raise ShareCountRetentionError("current signed head sequence is detached")
    return AuthenticatedCurrentSelection(head=dict(head), head_token=value.head_token, receipt=receipt)


def _validate_receipt(value: Any, *, label: str) -> dict[str, Any]:
    _validate_contract(value, "capital_structure_share_count_materialization_receipt.schema.json", label=label)
    if value.get("schema") != V2_RECEIPT_SCHEMA:
        raise ShareCountRetentionError(f"{label} is malformed")
    receipt_id = value.get("receipt_id")
    sequence = value.get("sequence")
    generation = value.get("generation")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1 or not isinstance(generation, Mapping):
        raise ShareCountRetentionError(f"{label} is malformed")
    _id_digest(receipt_id, V2_RECEIPT_ID_PREFIX, label)
    if receipt_id != _publication_receipt_id(value):
        raise ShareCountRetentionError(f"{label} identity is detached")
    generation_id = generation.get("generation_id")
    digest = _id_digest(generation_id, V2_GENERATION_ID_PREFIX, f"{label} generation")
    if generation.get("ledger_sha256") != digest:
        raise ShareCountRetentionError(f"{label} generation is detached")
    previous = value.get("previous_receipt")
    if sequence == 1:
        if previous is not None:
            raise ShareCountRetentionError(f"{label} genesis predecessor is malformed")
    else:
        if not isinstance(previous, Mapping) or set(previous) != {"sequence", "receipt_id", "receipt_sha256", "receipt_byte_length"}:
            raise ShareCountRetentionError(f"{label} predecessor is missing")
        _id_digest(previous.get("receipt_id"), V2_RECEIPT_ID_PREFIX, f"{label} predecessor")
        if (
            not isinstance(previous.get("receipt_sha256"), str)
            or not _HEX64.fullmatch(previous["receipt_sha256"])
            or not isinstance(previous.get("receipt_byte_length"), int)
            or isinstance(previous["receipt_byte_length"], bool)
            or previous["receipt_byte_length"] < 1
        ):
            raise ShareCountRetentionError(f"{label} predecessor is malformed")
        if previous["sequence"] != sequence - 1:
            raise ShareCountRetentionError(f"{label} predecessor sequence is detached")
        ancestors = value.get("ancestor_refs")
        if not isinstance(ancestors, list) or not ancestors or ancestors[0] != previous:
            raise ShareCountRetentionError(f"{label} immediate predecessor proof is detached")
    return dict(value)


def _validate_contract(record: Any, filename: str, *, label: str) -> None:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        schema_path = Path(__file__).resolve().parents[2] / "contracts" / filename
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(record))
    except ShareCountRetentionError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ShareCountRetentionError(f"{label} contract is unavailable") from exc
    if errors:
        detail = "; ".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors[:4]
        )
        raise ShareCountRetentionError(f"{label} contract violation: {detail}")


def _publication_receipt_id(record: Mapping[str, Any]) -> str:
    material = dict(record)
    material.pop("receipt_id", None)
    auth = material.get("auth")
    if not isinstance(auth, Mapping):
        raise ShareCountRetentionError("publication receipt authentication is malformed")
    material["auth"] = {key: value for key, value in auth.items() if key != "signature"}
    return V2_RECEIPT_ID_PREFIX + sha256(_canonical_bytes(material)).hexdigest()


def _validate_object(value: Any, *, label: str) -> RetentionObject:
    if not isinstance(value, RetentionObject):
        raise ShareCountRetentionError(f"{label} is malformed")
    if not _LEDGER_KEY.fullmatch(value.key):
        raise ShareCountRetentionError("unknown object key in generation-ledger listing")
    digest = _LEDGER_KEY.fullmatch(value.key).group(1)  # type: ignore[union-attr]
    if not _HEX64.fullmatch(digest) or not isinstance(value.etag, str) or not value.etag:
        raise ShareCountRetentionError(f"{label} is malformed")
    _aware(value.last_modified, f"{label} LastModified")
    return value


def _require_generation_ledger_key(key: Any, *, label: str) -> None:
    if not isinstance(key, str) or not _LEDGER_KEY.fullmatch(key):
        raise ShareCountRetentionError(f"{label} key is outside the exact v2 generation-ledger namespace")


def _r2_object(value: Any, *, label: str) -> RetentionObject:
    if not isinstance(value, Mapping):
        raise ShareCountRetentionError(f"{label} object is malformed")
    item = RetentionObject(
        key=value.get("Key"), last_modified=value.get("LastModified"), etag=value.get("ETag"),
    )
    return _validate_object(item, label=label)


def _require_r2_status(value: Any, *, allowed: set[int], label: str, ambiguity: bool = False) -> None:
    metadata = value.get("ResponseMetadata") if isinstance(value, Mapping) else None
    status = metadata.get("HTTPStatusCode") if isinstance(metadata, Mapping) else None
    if not isinstance(status, int) or isinstance(status, bool) or status not in allowed:
        error = ShareCountRetentionDeleteAmbiguity if ambiguity else ShareCountRetentionError
        raise error(f"{label} response status is malformed or unexpected")


def _aware(value: Any, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ShareCountRetentionError(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _validate_limits(quarantine_seconds: int, max_pages: int, max_objects: int, page_size: int) -> None:
    if isinstance(quarantine_seconds, bool) or not isinstance(quarantine_seconds, int) or quarantine_seconds < MIN_QUARANTINE_SECONDS:
        raise ShareCountRetentionError("retention quarantine must be at least 48 hours")
    for value, label in ((max_pages, "page"), (max_objects, "object"), (page_size, "page-size")):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ShareCountRetentionError(f"retention {label} cap is invalid")


def _id_digest(value: Any, prefix: str, label: str) -> str:
    if not isinstance(value, str) or not value.startswith(prefix) or not _HEX64.fullmatch(value[len(prefix):]):
        raise ShareCountRetentionError(f"{label} identity is invalid")
    return value[len(prefix):]


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ShareCountRetentionError("retention receipt is not canonical JSON data") from exc


def _output_authority() -> dict[str, bool]:
    return {
        "is_context_only": True, "share_count_ledger_authority": False,
        "instrument_authority": False, "capacity_authority": False,
        "runway_authority": False, "risk_authority": False, "rank_authority": False,
        "sizing_authority": False, "entry_authority": False, "trade_authority": False,
        "prophet_authority": False,
    }


def _signed_receipt(*, plan: RetentionPlan, deleted_keys: Sequence[str], apply: bool, signer: RetentionReceiptSigner) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema": RETENTION_RECEIPT_SCHEMA, "receipt_id": "", "created_at": _iso(plan.planned_at),
        "mode": "apply" if apply else "dry_run", "head_token_sha256": sha256(plan.head_token.encode("utf-8")).hexdigest(),
        "selected_receipt_id": plan.head_receipt_id,
        "protected_generation_keys": sorted(plan.protected_generation_keys),
        "candidate_generation_keys": [item.key for item in plan.candidate_objects],
        "grace_generation_keys": [item.key for item in plan.grace_objects],
        "deleted_generation_keys": list(deleted_keys), "quarantine_seconds": plan.quarantine_seconds,
        "output_authority": _output_authority(),
        "auth": {"scheme": RETENTION_AUTH_SCHEME, "key_id": signer.key_id, "signature": ""},
    }
    identity = dict(record); identity.pop("receipt_id"); identity["auth"] = {"scheme": RETENTION_AUTH_SCHEME, "key_id": signer.key_id}
    record["receipt_id"] = "retention:cs-share-count-v2:" + sha256(_canonical_bytes(identity)).hexdigest()
    payload = _receipt_auth_payload(record)
    record["auth"]["signature"] = signer.sign(payload)
    _validate_retention_receipt(record, signer=signer)
    return record


def _receipt_auth_payload(record: Mapping[str, Any]) -> bytes:
    material = dict(record); auth = material.get("auth")
    if not isinstance(auth, Mapping):
        raise ShareCountRetentionError("retention receipt auth is malformed")
    material["auth"] = {key: value for key, value in auth.items() if key != "signature"}
    return _canonical_bytes({"domain": RETENTION_RECEIPT_SCHEMA, "receipt": material})


def _validate_retention_receipt(record: Mapping[str, Any], *, signer: RetentionReceiptSigner | None) -> None:
    required = {"schema", "receipt_id", "created_at", "mode", "head_token_sha256", "selected_receipt_id", "protected_generation_keys", "candidate_generation_keys", "grace_generation_keys", "deleted_generation_keys", "quarantine_seconds", "output_authority", "auth"}
    if not isinstance(record, Mapping) or set(record) != required or record.get("schema") != RETENTION_RECEIPT_SCHEMA:
        raise ShareCountRetentionError("retention receipt is malformed")
    _validate_contract(record, "capital_structure_share_count_retention_receipt.schema.json", label="retention receipt")
    if not isinstance(record.get("receipt_id"), str) or not record["receipt_id"].startswith("retention:cs-share-count-v2:") or not _HEX64.fullmatch(record["receipt_id"].rsplit(":", 1)[-1]):
        raise ShareCountRetentionError("retention receipt identity is malformed")
    identity = dict(record)
    identity.pop("receipt_id")
    auth_for_id = identity.get("auth")
    if not isinstance(auth_for_id, Mapping):
        raise ShareCountRetentionError("retention receipt auth is malformed")
    identity["auth"] = {"scheme": auth_for_id.get("scheme"), "key_id": auth_for_id.get("key_id")}
    expected_id = "retention:cs-share-count-v2:" + sha256(_canonical_bytes(identity)).hexdigest()
    if record["receipt_id"] != expected_id:
        raise ShareCountRetentionError("retention receipt identity is detached")
    if record.get("mode") not in {"dry_run", "apply"} or record.get("output_authority") != _output_authority():
        raise ShareCountRetentionError("retention receipt authority/mode is malformed")
    _validate_limits(record.get("quarantine_seconds"), 1, 1, 1)
    _id_digest(record.get("selected_receipt_id"), V2_RECEIPT_ID_PREFIX, "retention selected receipt")
    if not isinstance(record.get("head_token_sha256"), str) or not _HEX64.fullmatch(record["head_token_sha256"]):
        raise ShareCountRetentionError("retention receipt head token digest is malformed")
    lists: dict[str, set[str]] = {}
    for field, maximum in (("protected_generation_keys", 2), ("candidate_generation_keys", DEFAULT_MAX_OBJECTS), ("grace_generation_keys", DEFAULT_MAX_OBJECTS), ("deleted_generation_keys", DEFAULT_MAX_OBJECTS)):
        value = record.get(field)
        if not isinstance(value, list) or not value or (field != "protected_generation_keys" and value is None) or len(value) > maximum:
            if field in {"candidate_generation_keys", "grace_generation_keys", "deleted_generation_keys"} and value == []:
                lists[field] = set()
                continue
            raise ShareCountRetentionError(f"retention receipt {field} is malformed")
        if len(value) != len(set(value)):
            raise ShareCountRetentionError(f"retention receipt {field} is not unique")
        for key in value:
            _require_generation_ledger_key(key, label=f"retention receipt {field}")
        lists[field] = set(value)
    if lists["candidate_generation_keys"] & lists["grace_generation_keys"]:
        raise ShareCountRetentionError("retention receipt candidate/grace sets overlap")
    if lists["protected_generation_keys"] & (lists["candidate_generation_keys"] | lists["grace_generation_keys"] | lists["deleted_generation_keys"]):
        raise ShareCountRetentionError("retention receipt includes a protected generation in a mutable set")
    if not lists["deleted_generation_keys"].issubset(lists["candidate_generation_keys"]):
        raise ShareCountRetentionError("retention receipt deleted set is not a candidate subset")
    if record["mode"] == "dry_run" and lists["deleted_generation_keys"]:
        raise ShareCountRetentionError("dry-run retention receipt claims deletion")
    auth = record.get("auth")
    if not isinstance(auth, Mapping) or set(auth) != {"scheme", "key_id", "signature"} or auth.get("scheme") != RETENTION_AUTH_SCHEME:
        raise ShareCountRetentionError("retention receipt auth is malformed")
    if signer is not None and not signer.verify(_receipt_auth_payload(record), auth.get("signature"), key_id=auth.get("key_id")):
        raise ShareCountRetentionError("retention receipt authentication mismatch")


def _iso(value: datetime) -> str:
    return _aware(value, "retention receipt timestamp").isoformat().replace("+00:00", "Z")


__all__ = [
    "AuthenticatedCurrentSelection", "AuthenticatedReceipt", "AuthenticatedShareCountReader",
    "PublicationReadBoundary", "PublisherV2RetentionReader", "R2RetentionObjectStore",
    "RETENTION_R2_ENV_NAMES", "build_dedicated_r2_retention_store",
    "ConditionalDeleteResult", "DEFAULT_MAX_OBJECTS", "DEFAULT_MAX_PAGES", "DEFAULT_PAGE_SIZE",
    "DEFAULT_QUARANTINE_SECONDS", "HmacRetentionReceiptSigner", "MIN_QUARANTINE_SECONDS",
    "RetentionListPage", "RetentionObject", "RetentionObjectStore", "RetentionPlan",
    "RetentionRunResult", "ShareCountRetentionDeleteAmbiguity", "ShareCountRetentionError",
    "ShareCountRetentionHeadChanged", "V2_GENERATION_OBJECT_PREFIX", "build_retention_plan",
    "generation_ledger_key", "run_retention", "write_retention_receipt",
]
