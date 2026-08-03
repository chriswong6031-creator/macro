"""Sealed, filing-backed overlays for immutable v1 query snapshots.

``ffqsv2_`` is deliberately an overlay, never an upgrade-in-place of the
existing ``ffqs_`` receipt.  It records only the small claim this lane can
honestly make: a selected Company Facts raw occurrence corresponded exactly to
one B3 selected-member / Company-Facts projection.  It does not turn the raw
occurrence's unknown dimensions into XBRL dimensions, and does not make a
filing-completeness or trading-authority claim.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from collections import OrderedDict
from hashlib import sha256
import hmac
import json
import re
from threading import Event, RLock
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from engine.research_vault.r2_store import StrictBoundedReadStore

from .companyfacts_ledger import (
    CompanyFactsLedgerConversion,
    CompanyFactsLedgerOccurrence,
    CompanyFactsLedgerReceipt,
    SubmissionSourceWitness,
)
from .filing_attestation import (
    CompanyFactsSourcePaths,
    FilingAttestation,
    FilingAttestationError,
    PinnedSourceAuthority,
    verify_filing_attestation_source,
)
from .filing_package import FilingPackage
from .ixbrl_extraction import IxbrlExtraction
from .query_snapshots import (
    HARD_MAX_SNAPSHOT_LEDGER_BYTES,
    HARD_MAX_SNAPSHOT_MANIFEST_BYTES,
    HARD_MAX_SNAPSHOT_MATRIX_BYTES,
    HARD_MAX_SNAPSHOT_METADATA_BYTES,
    HARD_MAX_SNAPSHOT_PARQUET_BYTES,
    QUERY_SNAPSHOT_PREFIX,
    QuerySnapshot,
    QuerySnapshotError,
    verify_query_snapshot,
)
from .raw_ledger import (
    AvailabilityStatus,
    RawFactLedger,
    RawFactOccurrence,
    canonical_json,
    decimal_text,
    parse_utc,
    stable_id,
    utc_text,
)


ATTESTED_QUERY_SNAPSHOT_SCHEMA = "fundamental_forensics.attested_query_snapshot/v2"
ATTESTED_QUERY_SNAPSHOT_POINTER_SCHEMA = "fundamental_forensics.attested_query_snapshot_pointer/v2"
ATTESTED_QUERY_SNAPSHOT_PREFIX = "fundamental_forensics/attested-query-snapshots/v2"
ATTESTED_QUERY_SNAPSHOT_ID_PREFIX = "ffqsv2_"
ATTESTED_QUERY_SNAPSHOT_PUBLICATION_CONTRACT = "single_writer_operator_only"
ATTESTED_QUERY_SNAPSHOT_POLICY_VERSION = "ffqsv2_exact_join/v1"
ATTESTED_QUERY_SNAPSHOT_POLICY_FINGERPRINT = "6e4ba04cf9c775ac280ba1426985246ffbdf730222b4521c4b26a41f5623871a"

HARD_MAX_ATTESTED_SNAPSHOT_MANIFEST_BYTES = 4 * 1024 * 1024
HARD_MAX_ATTESTED_SNAPSHOT_ATTESTATIONS_BYTES = 32 * 1024 * 1024
HARD_MAX_ATTESTED_SNAPSHOT_BINDINGS_BYTES = 32 * 1024 * 1024
HARD_MAX_ATTESTED_SNAPSHOT_COVERAGE_BYTES = 32 * 1024 * 1024
HARD_MAX_ATTESTED_SNAPSHOT_CONVERSION_BYTES = 256 * 1024 * 1024
HARD_MAX_ATTESTED_SNAPSHOT_TOTAL_BYTES = 512 * 1024 * 1024
HARD_MAX_ATTESTED_SNAPSHOT_ATTESTATIONS = 10_000
HARD_MAX_ATTESTED_SNAPSHOT_BINDINGS = 250_000
HARD_MAX_ATTESTED_SNAPSHOT_ROOT_CELLS = 100_000
HARD_MAX_ATTESTED_JSON_NODES = 300_000
HARD_MAX_ATTESTED_CONVERSION_JSON_NODES = 5_000_000
HARD_MAX_ATTESTED_JSON_DEPTH = 64
HARD_MAX_ATTESTED_JSON_TEXT_BYTES = 1 * 1024 * 1024

# The v2 publication format can retain large private artifacts so an operator
# can reproduce a full verification offline.  The HTTP receipt reader is a
# deliberately narrower product surface: its two compact artifacts must fit a
# much smaller pre-read budget and a bounded decoded index.  These are serving
# limits, not a change to what a valid immutable v2 publication may retain.
HARD_MAX_ATTESTED_RECEIPT_COMPACT_BYTES = 2 * 1024 * 1024
HARD_MAX_ATTESTED_RECEIPT_PROJECTIONS = 5_000
HARD_MAX_ATTESTED_RECEIPT_BINDINGS = 20_000
HARD_MAX_ATTESTED_RECEIPT_ROOT_CELLS = 10_000
HARD_MAX_ATTESTED_RECEIPT_LEAF_REFERENCES = 40_000
HARD_MAX_ATTESTED_RECEIPT_DECODED_INDEX_BYTES = 16 * 1024 * 1024

_ID_RE = re.compile(r"^ffqsv2_[a-f0-9]{64}$")
_V1_ID_RE = re.compile(r"^ffqs_[a-f0-9]{64}$")
_ATTESTATION_ID_RE = re.compile(r"^ffatt_[a-f0-9]{64}$")
_MATCH_ID_RE = re.compile(r"^ffatt_match_[a-f0-9]{64}$")
_SHA_RE = re.compile(r"^[a-f0-9]{64}$")
_RAW_OCCURRENCE_ID_RE = re.compile(r"^rawfact_[a-f0-9]{64}$")
_ROOT_CELL_ID_RE = re.compile(r"^metric_cell_[a-f0-9]{64}$")
_SOURCE_SNAPSHOT_ID_RE = re.compile(r"^ffsecsrc_[a-f0-9]{64}$")
_PACKAGE_ID_RE = re.compile(r"^ffpkg_[a-f0-9]{64}$")
_EXTRACTION_ID_RE = re.compile(r"^ffxbrl_[a-f0-9]{64}$")
_COMPANYFACTS_CAPTURE_ID_RE = re.compile(r"^ffseccfc_[a-f0-9]{64}$")
_COMPANYFACTS_MANIFEST_ID_RE = re.compile(r"^ffseccfm_[a-f0-9]{64}$")
_CIK_RE = re.compile(r"^[0-9]{10}$")
_ACCESSION_RE = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_ROLES = ("attestations_json", "companyfacts_conversion_json", "bindings_json", "coverage_json")
_ROLE_CONTENT_TYPES = {role: "application/json" for role in _ROLES}
_ROLE_LIMITS = {
    "attestations_json": HARD_MAX_ATTESTED_SNAPSHOT_ATTESTATIONS_BYTES,
    "companyfacts_conversion_json": HARD_MAX_ATTESTED_SNAPSHOT_CONVERSION_BYTES,
    "bindings_json": HARD_MAX_ATTESTED_SNAPSHOT_BINDINGS_BYTES,
    "coverage_json": HARD_MAX_ATTESTED_SNAPSHOT_COVERAGE_BYTES,
}
_V1_ROLE_LIMITS = {
    "matrix_json": HARD_MAX_SNAPSHOT_MATRIX_BYTES,
    "ledger_json": HARD_MAX_SNAPSHOT_LEDGER_BYTES,
    "filing_metadata_json": HARD_MAX_SNAPSHOT_METADATA_BYTES,
    "cells_parquet": HARD_MAX_SNAPSHOT_PARQUET_BYTES,
}
_PUBLISH_LOCK = RLock()
_RECEIPT_INDEX_CACHE_LOCK = RLock()
_RECEIPT_INDEX_CACHE: OrderedDict[tuple[int, str], tuple[StrictBoundedReadStore, AttestedQueryReceiptIndex, int]] = OrderedDict()
_RECEIPT_INDEX_CACHE_MAX_ENTRIES = 4
_RECEIPT_INDEX_CACHE_MAX_BYTES = HARD_MAX_ATTESTED_RECEIPT_DECODED_INDEX_BYTES
_RECEIPT_INDEX_CACHE_BYTES = 0
_RECEIPT_INDEX_SINGLEFLIGHT_STRIPE_COUNT = 32
_MAPPINGPROXY_TYPE = type(MappingProxyType({}))
_JSON_SEQUENCE_TYPES = (list, tuple)


class AttestedQuerySnapshotError(RuntimeError):
    """An attested-query overlay is malformed, incomplete, or untrustworthy."""


@dataclass(frozen=True)
class AttestationMaterial:
    """The external objects required to renew one stored B3 attestation."""

    attestation: FilingAttestation
    package: FilingPackage
    extraction: IxbrlExtraction
    authority: PinnedSourceAuthority
    companyfacts_paths: CompanyFactsSourcePaths | None = None


@dataclass(frozen=True)
class AttestedOccurrenceBinding:
    """An explicit selected occurrence -> one B3 Company Facts match choice."""

    occurrence_id: str
    attestation_id: str
    match_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.occurrence_id, str) or not self.occurrence_id:
            raise AttestedQuerySnapshotError("occurrence binding occurrence_id is invalid")
        if not isinstance(self.attestation_id, str) or not _ATTESTATION_ID_RE.fullmatch(self.attestation_id):
            raise AttestedQuerySnapshotError("occurrence binding attestation_id is invalid")
        if not isinstance(self.match_id, str) or not _MATCH_ID_RE.fullmatch(self.match_id):
            raise AttestedQuerySnapshotError("occurrence binding match_id is invalid")

    def to_dict(self) -> dict[str, str]:
        return {"occurrence_id": self.occurrence_id, "attestation_id": self.attestation_id, "match_id": self.match_id}


@dataclass(frozen=True)
class AttestedQuerySnapshotArtifact:
    role: str
    object_key: str
    sha256: str
    byte_length: int
    content_type: str

    def __post_init__(self) -> None:
        if self.role not in _ROLES:
            raise AttestedQuerySnapshotError("unsupported attested snapshot artifact role")
        _key(self.object_key)
        if self.object_key != _object_key(self.sha256) or not _SHA_RE.fullmatch(self.sha256):
            raise AttestedQuerySnapshotError("attested snapshot artifact does not bind its digest")
        if isinstance(self.byte_length, bool) or not isinstance(self.byte_length, int) or not 0 <= self.byte_length <= _ROLE_LIMITS[self.role]:
            raise AttestedQuerySnapshotError("attested snapshot artifact byte length is invalid")
        if self.content_type != _ROLE_CONTENT_TYPES[self.role]:
            raise AttestedQuerySnapshotError("attested snapshot artifact content type is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role, "object_key": self.object_key, "sha256": self.sha256, "byte_length": self.byte_length, "content_type": self.content_type}


@dataclass(frozen=True)
class AttestedQuerySnapshotPointer:
    snapshot_id: str
    manifest_key: str
    base_snapshot_id: str
    published_at: datetime | str
    schema: str = ATTESTED_QUERY_SNAPSHOT_POINTER_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != ATTESTED_QUERY_SNAPSHOT_POINTER_SCHEMA:
            raise AttestedQuerySnapshotError("unsupported attested snapshot pointer")
        _snapshot_id(self.snapshot_id)
        if self.manifest_key != _manifest_key(self.snapshot_id):
            raise AttestedQuerySnapshotError("attested snapshot pointer manifest key is invalid")
        _v1_snapshot_id(self.base_snapshot_id)
        object.__setattr__(self, "published_at", _utc(self.published_at, field="pointer.published_at"))

    def to_dict(self) -> dict[str, str]:
        return {"schema": self.schema, "snapshot_id": self.snapshot_id, "manifest_key": self.manifest_key, "base_snapshot_id": self.base_snapshot_id, "published_at": utc_text(self.published_at) or ""}

    def to_json_bytes(self) -> bytes:
        return canonical_json(self.to_dict()).encode("utf-8")


@dataclass(frozen=True)
class PreparedAttestedQuerySnapshot:
    snapshot_id: str
    manifest_key: str
    manifest: Mapping[str, Any]
    artifacts: tuple[AttestedQuerySnapshotArtifact, ...]
    payloads: Mapping[str, bytes]


@dataclass(frozen=True)
class AttestedQuerySnapshot:
    snapshot_id: str
    manifest_key: str
    manifest: Mapping[str, Any]
    base_snapshot: QuerySnapshot
    companyfacts_conversion: CompanyFactsLedgerConversion
    attestations: Mapping[str, Mapping[str, Any]]
    bindings: tuple[AttestedOccurrenceBinding, ...]
    cell_coverage: tuple[Mapping[str, Any], ...]

    @property
    def base_snapshot_id(self) -> str:
        return self.base_snapshot.snapshot_id

    @property
    def published_at(self) -> datetime:
        return _utc(self.manifest["clocks"]["published_at"], field="snapshot.published_at")


@dataclass(frozen=True)
class AttestedQueryReceiptIndex:
    """Small immutable receipt projection for the attested-history read API.

    This is deliberately *not* an :class:`AttestedQuerySnapshot`: it does not
    load the frozen v1 query snapshot, the B3 record bodies, or the full
    Company Facts conversion.  Its narrow promise is stored-receipt
    self-consistency, not a fresh source verification.
    """

    snapshot_id: str
    manifest_key: str
    base_snapshot_id: str
    query_hash: str
    manifest: Mapping[str, Any]
    roots: tuple[Mapping[str, Any], ...]
    root_ids: tuple[str, ...]
    roots_by_id: Mapping[str, Mapping[str, Any]]
    bindings_by_occurrence: Mapping[str, Mapping[str, Any]]
    attestations_by_id: Mapping[str, Mapping[str, Any]]
    published_at: datetime


@dataclass
class _ReceiptIndexFlight:
    """One active immutable receipt load, retained only until its waiters wake."""

    store: StrictBoundedReadStore
    snapshot_id: str
    done: Event
    index: AttestedQueryReceiptIndex | None = None
    error: BaseException | None = None


@dataclass
class _ReceiptIndexFlightStripe:
    """A bounded singleflight slot; collisions queue, never grow a key map."""

    lock: RLock
    flight: _ReceiptIndexFlight | None = None


# One bounded stripe per (store identity, snapshot id) coalesces an expensive
# cold receipt parse.  The active-flight result is separate from the LRU cache:
# every caller that joined this generation receives its exact outcome even if a
# tiny cache policy evicts the index before waiters run.
_RECEIPT_INDEX_SINGLEFLIGHT_STRIPES = tuple(
    _ReceiptIndexFlightStripe(lock=RLock())
    for _ in range(_RECEIPT_INDEX_SINGLEFLIGHT_STRIPE_COUNT)
)


# Implementation follows below.  Keeping the declarations first makes the
# public contract reviewable without allowing callers to construct a v2 record
# from unchecked dictionaries.


def _utc(value: datetime | str, *, field: str) -> datetime:
    try:
        parsed = parse_utc(value, field_name=field)
    except ValueError as exc:
        raise AttestedQuerySnapshotError(str(exc)) from exc
    if parsed is None:
        raise AttestedQuerySnapshotError(f"{field} is required")
    return parsed


def _snapshot_id(value: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise AttestedQuerySnapshotError("invalid attested query snapshot id")
    return value


def _v1_snapshot_id(value: str) -> str:
    if not isinstance(value, str) or not _V1_ID_RE.fullmatch(value):
        raise AttestedQuerySnapshotError("invalid base query snapshot id")
    return value


def _key(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith(ATTESTED_QUERY_SNAPSHOT_PREFIX + "/")
        or len(value) > 1024
        or "\\" in value
        or "\x00" in value
        or "?" in value
        or "#" in value
    ):
        raise AttestedQuerySnapshotError("attested snapshot key is unsafe")
    if any(not part or part in {".", ".."} for part in value.split("/")):
        raise AttestedQuerySnapshotError("attested snapshot key is unsafe")
    return value


def _object_key(digest: str) -> str:
    if not isinstance(digest, str) or not _SHA_RE.fullmatch(digest):
        raise AttestedQuerySnapshotError("object digest must be lowercase SHA-256")
    return f"{ATTESTED_QUERY_SNAPSHOT_PREFIX}/objects/sha256/{digest[:2]}/{digest}.bin"


def _manifest_key(snapshot_id: str) -> str:
    return f"{ATTESTED_QUERY_SNAPSHOT_PREFIX}/manifests/{_snapshot_id(snapshot_id)}.json"


def _latest_key() -> str:
    return f"{ATTESTED_QUERY_SNAPSHOT_PREFIX}/latest.json"


def _artifact(role: str, payload: bytes) -> AttestedQuerySnapshotArtifact:
    if role not in _ROLES or not isinstance(payload, bytes) or len(payload) > _ROLE_LIMITS[role]:
        raise AttestedQuerySnapshotError("attested snapshot payload exceeds bounded role limit")
    digest = sha256(payload).hexdigest()
    return AttestedQuerySnapshotArtifact(
        role=role,
        object_key=_object_key(digest),
        sha256=digest,
        byte_length=len(payload),
        content_type=_ROLE_CONTENT_TYPES[role],
    )


def _strict_object(value: Any, *, field: str, required: frozenset[str]) -> dict[str, Any]:
    if type(value) not in (dict, _MAPPINGPROXY_TYPE) or set(value) != required:
        raise AttestedQuerySnapshotError(f"{field} shape is invalid")
    return {key: value[key] for key in required}


def _json_budget(value: Any, *, field: str, maximum_nodes: int = HARD_MAX_ATTESTED_JSON_NODES) -> None:
    """Reject hostile JSON-shaped values before canonicalization or publication."""
    pending: list[tuple[Any, int]] = [(value, 1)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > maximum_nodes:
            raise AttestedQuerySnapshotError(f"{field} exceeds JSON node safety limit")
        if depth > HARD_MAX_ATTESTED_JSON_DEPTH:
            raise AttestedQuerySnapshotError(f"{field} exceeds JSON depth safety limit")
        kind = type(current)
        if kind is str:
            if len(current.encode("utf-8")) > HARD_MAX_ATTESTED_JSON_TEXT_BYTES:
                raise AttestedQuerySnapshotError(f"{field} contains oversized JSON text")
        elif kind in (type(None), bool, int):
            if kind is int and len(str(current)) > 4096:
                raise AttestedQuerySnapshotError(f"{field} contains oversized JSON integer")
        elif kind in (dict, _MAPPINGPROXY_TYPE):
            for key, item in current.items():
                if type(key) is not str or len(key.encode("utf-8")) > HARD_MAX_ATTESTED_JSON_TEXT_BYTES:
                    raise AttestedQuerySnapshotError(f"{field} contains an invalid JSON key")
                pending.append((item, depth + 1))
        elif kind in (list, tuple):
            pending.extend((item, depth + 1) for item in current)
        else:
            raise AttestedQuerySnapshotError(f"{field} contains a non-JSON nominal")


def _freeze(value: Any) -> Any:
    if type(value) in (dict, _MAPPINGPROXY_TYPE):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if type(value) in (list, tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _json_object(payload: bytes, *, field: str, limit: int, maximum_nodes: int = HARD_MAX_ATTESTED_JSON_NODES) -> dict[str, Any]:
    if not isinstance(payload, bytes) or len(payload) > limit:
        raise AttestedQuerySnapshotError(f"{field} exceeds byte safety limit")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in items:
            if key in result:
                raise AttestedQuerySnapshotError(f"{field} contains duplicate JSON key")
            result[key] = item
        return result

    def constant(value: str) -> None:
        raise AttestedQuerySnapshotError(f"{field} contains non-finite JSON constant: {value}")

    def parse_int(value: str) -> int:
        if len(value.lstrip("-")) > 4096:
            raise AttestedQuerySnapshotError(f"{field} contains oversized JSON integer")
        return int(value)

    def reject_float(value: str) -> None:
        raise AttestedQuerySnapshotError(f"{field} must not contain JSON floats")

    try:
        decoded = json.loads(payload.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant, parse_int=parse_int, parse_float=reject_float)
    except AttestedQuerySnapshotError:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise AttestedQuerySnapshotError(f"{field} is not UTF-8 JSON") from exc
    if not isinstance(decoded, dict):
        raise AttestedQuerySnapshotError(f"{field} must be an object")
    _json_budget(decoded, field=field, maximum_nodes=maximum_nodes)
    return decoded


def _canonical_payload(value: Mapping[str, Any], *, field: str, limit: int, maximum_nodes: int = HARD_MAX_ATTESTED_JSON_NODES) -> bytes:
    _json_budget(value, field=field, maximum_nodes=maximum_nodes)
    try:
        payload = canonical_json(dict(value)).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AttestedQuerySnapshotError(f"{field} cannot be canonically encoded") from exc
    if len(payload) > limit:
        raise AttestedQuerySnapshotError(f"{field} exceeds byte safety limit")
    return payload


def _read_bounded(store: StrictBoundedReadStore, key: str, *, maximum: int, required: bool = True) -> bytes | None:
    try:
        payload = store.get_bytes_strict_bounded(key, maximum)
    except Exception as exc:  # noqa: BLE001 - strict stores deliberately surface all operational failure.
        raise AttestedQuerySnapshotError(f"strict bounded read failed for {key}") from exc
    if payload is None:
        if required:
            raise AttestedQuerySnapshotError(f"required private object is missing: {key}")
        return None
    if not isinstance(payload, bytes) or len(payload) > maximum:
        raise AttestedQuerySnapshotError(f"private object violates bounded read contract: {key}")
    return payload


def _read_exact_bounded(
    store: StrictBoundedReadStore,
    key: str,
    *,
    expected_byte_length: int,
    maximum: int,
) -> bytes:
    """Read through the public cap-only contract, then require exact bytes.

    ``StrictBoundedReadStore`` deliberately promises only a cap argument.  A
    couple of first-party stores offer a non-protocol exact-length extension,
    but receipt serving cannot claim the public protocol and then require that
    private signature at runtime.  Passing the manifest-declared length as the
    cap still prevents a compliant store from returning an oversized body; the
    exact equality check immediately below rejects a short/truncated body.
    """
    if (
        isinstance(expected_byte_length, bool)
        or not isinstance(expected_byte_length, int)
        or expected_byte_length < 0
        or isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or expected_byte_length > maximum
    ):
        raise AttestedQuerySnapshotError("attested receipt exact read boundary is invalid")
    payload = _read_bounded(store, key, maximum=expected_byte_length)
    if len(payload) != expected_byte_length:
        raise AttestedQuerySnapshotError(f"private object violates exact bounded read contract: {key}")
    return payload


def _require_store(store: Any) -> StrictBoundedReadStore:
    if not isinstance(store, StrictBoundedReadStore):
        raise AttestedQuerySnapshotError("attested query snapshots require a StrictBoundedReadStore")
    return store


def _v1_manifest_key(snapshot_id: str) -> str:
    return f"{QUERY_SNAPSHOT_PREFIX}/manifests/{_v1_snapshot_id(snapshot_id)}.json"


class _FrozenV1ReplayStore:
    """Minimal strict-read adapter backed only by B4's bounded byte cache."""

    def __init__(self, payloads: Mapping[str, bytes]) -> None:
        self._payloads = dict(payloads)

    def get_bytes_strict(self, key: str) -> bytes | None:
        # Return a fresh immutable bytes object conceptually, not a new remote
        # read. ``bytes`` itself is immutable so the cached value is safe.
        return self._payloads.get(key)

    # ``StrictReadStore`` inherits the legacy Store protocol.  v1 replay uses
    # only the strict method, but these methods keep its runtime structural
    # check honest and make any unexpected operation fail closed.
    def get_bytes(self, key: str) -> bytes | None:
        return self._payloads.get(key)

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> bool:
        del key, data, content_type
        raise AttestedQuerySnapshotError("v1 replay store is immutable")

    def list_prefix(self, prefix: str) -> list[str]:
        return sorted(key for key in self._payloads if key.startswith(prefix))

    def exists(self, key: str) -> bool:
        return key in self._payloads

    def upload_time(self, key: str) -> str | None:
        del key
        return None


def _preflight_base_snapshot(store: StrictBoundedReadStore, snapshot_id: str) -> Mapping[str, bytes]:
    """Bound every v1 object before invoking its legacy verification replay.

    The v1 verifier predates ``StrictBoundedReadStore`` and re-reads objects via
    its unbounded strict method.  B4 therefore requires a bounded store and
    preflights exactly the declared manifest/object set first.  The subsequent
    v1 replay remains required for the actual receipt proof; changing that
    shared API is intentionally outside this additive overlay.
    """
    manifest_key = _v1_manifest_key(snapshot_id)
    raw = _read_bounded(store, manifest_key, maximum=HARD_MAX_SNAPSHOT_MANIFEST_BYTES)
    manifest = _json_object(raw, field="base query snapshot manifest", limit=HARD_MAX_SNAPSHOT_MANIFEST_BYTES)
    if manifest.get("snapshot_id") != snapshot_id or not isinstance(manifest.get("objects"), list):
        raise AttestedQuerySnapshotError("base query snapshot manifest does not bind requested snapshot")
    objects = manifest["objects"]
    if len(objects) != len(_V1_ROLE_LIMITS):
        raise AttestedQuerySnapshotError("base query snapshot manifest object count is invalid")
    roles: set[str] = set()
    cache: dict[str, bytes] = {manifest_key: raw}
    for item in objects:
        if not isinstance(item, Mapping):
            raise AttestedQuerySnapshotError("base query snapshot artifact is invalid")
        role = item.get("role")
        key = item.get("object_key")
        digest = item.get("sha256")
        byte_length = item.get("byte_length")
        if role not in _V1_ROLE_LIMITS or role in roles or not isinstance(key, str) or not isinstance(digest, str) or not _SHA_RE.fullmatch(digest):
            raise AttestedQuerySnapshotError("base query snapshot artifact is invalid")
        if isinstance(byte_length, bool) or not isinstance(byte_length, int) or byte_length < 0 or byte_length > _V1_ROLE_LIMITS[role]:
            raise AttestedQuerySnapshotError("base query snapshot artifact exceeds bounded limit")
        payload = _read_bounded(store, key, maximum=_V1_ROLE_LIMITS[role])
        if len(payload) != byte_length or sha256(payload).hexdigest() != digest:
            raise AttestedQuerySnapshotError("base query snapshot artifact digest mismatch")
        cache[key] = payload
        roles.add(role)
    if roles != set(_V1_ROLE_LIMITS):
        raise AttestedQuerySnapshotError("base query snapshot role set is invalid")
    return MappingProxyType(cache)


def _verified_base_snapshot(store: StrictBoundedReadStore, snapshot_id: str) -> QuerySnapshot:
    cache = _preflight_base_snapshot(store, snapshot_id)
    try:
        # Never hand the legacy v1 verifier the mutable remote store after this
        # point: it only receives the exact bounded bytes whose hashes we just
        # checked. This closes both unbounded re-read and read-after-preflight
        # substitution paths without mutating v1 in this additive lane.
        base = verify_query_snapshot(_FrozenV1ReplayStore(cache), snapshot_id=snapshot_id)
    except (QuerySnapshotError, TypeError, ValueError) as exc:
        raise AttestedQuerySnapshotError(f"base query snapshot cannot be replay-verified: {exc}") from exc
    if base.snapshot_id != snapshot_id:
        raise AttestedQuerySnapshotError("base query snapshot verifier returned the wrong snapshot")
    # The v1 schema has a publication clock but no history catalogue; B4 proves
    # this immutable, readable receipt was produced after its own computation,
    # not that it is the current v1 pointer.
    clocks = base.manifest.get("clocks")
    if not isinstance(clocks, Mapping):
        raise AttestedQuerySnapshotError("base query snapshot has no clocks")
    published = _utc(clocks.get("published_at"), field="base.published_at")
    computed = _utc(clocks.get("computed_at"), field="base.computed_at")
    if published < computed:
        raise AttestedQuerySnapshotError("base query snapshot publication clock is invalid")
    return base


def _material_record(material: AttestationMaterial) -> dict[str, Any]:
    if type(material) is not AttestationMaterial:
        raise AttestedQuerySnapshotError("attestation materials must be exact AttestationMaterial values")
    if type(material.attestation) is not FilingAttestation:
        raise AttestedQuerySnapshotError("attestation material must carry an exact FilingAttestation")
    if type(material.package) is not FilingPackage or type(material.extraction) is not IxbrlExtraction:
        raise AttestedQuerySnapshotError("attestation material package/extraction types are invalid")
    if type(material.authority) is not PinnedSourceAuthority:
        raise AttestedQuerySnapshotError("attestation material authority must be an exact PinnedSourceAuthority")
    if material.companyfacts_paths is not None and type(material.companyfacts_paths) is not CompanyFactsSourcePaths:
        raise AttestedQuerySnapshotError("attestation material Company Facts paths type is invalid")
    try:
        verify_filing_attestation_source(
            material.attestation,
            material.package,
            material.extraction,
            authority=material.authority,
            companyfacts_paths=material.companyfacts_paths,
        )
    except (FilingAttestationError, TypeError, ValueError) as exc:
        raise AttestedQuerySnapshotError(f"filing attestation source replay failed: {exc}") from exc
    record = material.attestation.to_dict()
    if record["company_facts"]["requested"] is not True or not record["company_facts"]["matches"]:
        raise AttestedQuerySnapshotError("attestation material needs a positive B3 Company Facts projection")
    return record


def _material_map(materials: Sequence[AttestationMaterial]) -> dict[str, dict[str, Any]]:
    if type(materials) is not tuple:
        raise AttestedQuerySnapshotError("attestation_materials must be an immutable tuple")
    if not materials or len(materials) > HARD_MAX_ATTESTED_SNAPSHOT_ATTESTATIONS:
        raise AttestedQuerySnapshotError("attestation material count is invalid")
    out: dict[str, dict[str, Any]] = {}
    for material in materials:
        record = _material_record(material)
        key = record["attestation_id"]
        if key in out:
            raise AttestedQuerySnapshotError("duplicate filing attestation material")
        out[key] = record
    return out


def _selected_raw_occurrences(base: QuerySnapshot) -> tuple[dict[str, RawFactOccurrence], dict[str, tuple[str, ...]]]:
    ledger_by_id = {item.occurrence_id: item for item in base.ledger.events}
    selected: dict[str, RawFactOccurrence] = {}
    roots: dict[str, tuple[str, ...]] = {}
    for cell in base.matrix.cells:
        leaves: set[str] = set()
        for node in cell.nodes:
            raw = node.provenance.selected_raw_fact
            if raw is None:
                continue
            ledger_raw = ledger_by_id.get(raw.occurrence_id)
            if ledger_raw is None or ledger_raw.to_dict() != raw.to_dict():
                raise AttestedQuerySnapshotError("selected raw fact does not exactly bind the frozen v1 ledger")
            selected[raw.occurrence_id] = raw
            leaves.add(raw.occurrence_id)
        roots[cell.cell_id] = tuple(sorted(leaves))
    return selected, roots


def _date_text(value: Any, *, field: str, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or len(value) != 10:
        raise AttestedQuerySnapshotError(f"{field} is invalid")
    # The B3 record already made the date semantic; only accept exact ISO text
    # here rather than accidentally canonicalizing a permissive input.
    try:
        from datetime import date
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise AttestedQuerySnapshotError(f"{field} is invalid") from exc
    if parsed.isoformat() != value:
        raise AttestedQuerySnapshotError(f"{field} is invalid")
    return value


def _binding_projection(
    *, occurrence: RawFactOccurrence, companion: CompanyFactsLedgerOccurrence, attestation: Mapping[str, Any], match: Mapping[str, Any]
) -> dict[str, Any]:
    """Join one unknown-dimension Company Facts row to one B3 correspondence."""
    cf = attestation["company_facts"]
    filing = attestation["filing"]
    receipt = companion.occurrence
    if occurrence.to_dict() != receipt.to_dict():
        raise AttestedQuerySnapshotError("bound selected raw fact differs from Company Facts conversion occurrence")
    if occurrence.source.source != "sec-companyfacts" or occurrence.dimensions_known is not False:
        raise AttestedQuerySnapshotError("only dimensions-unknown sec-companyfacts selected facts may be attested")
    if companion.occurrence.dimensions_known is not False:
        raise AttestedQuerySnapshotError("Company Facts conversion companion unexpectedly knows dimensions")
    if occurrence.source.entity_id != filing["cik"] or occurrence.source.accession != filing["accession"]:
        raise AttestedQuerySnapshotError("Company Facts occurrence does not bind attested filing identity")
    if occurrence.source.body_sha256 != cf["response_sha256"]:
        raise AttestedQuerySnapshotError("Company Facts occurrence response SHA does not bind attestation")
    expected_document_id = stable_id("sec_companyfacts_capture_document", cf["capture_id"])
    if occurrence.source.document_id != expected_document_id:
        raise AttestedQuerySnapshotError("Company Facts occurrence document does not bind attested capture")
    if occurrence.context.entity_scheme != "sec-cik" or occurrence.context.entity_identifier != filing["cik"]:
        raise AttestedQuerySnapshotError("Company Facts occurrence context does not bind attested entity")
    if occurrence.concept_qname != f"{companion.taxonomy}:{companion.concept}":
        raise AttestedQuerySnapshotError("Company Facts occurrence concept does not bind companion")
    start = companion.start
    end = companion.end
    context = occurrence.context
    if start is None:
        if (
            context.instant is None
            or context.instant.isoformat() != end
            or context.start is not None
            or context.end is not None
        ):
            raise AttestedQuerySnapshotError("Company Facts occurrence instant does not bind companion period")
    elif (
        context.instant is not None
        or context.start is None
        or context.end is None
        or context.start.isoformat() != start
        or context.end.isoformat() != end
    ):
        raise AttestedQuerySnapshotError("Company Facts occurrence duration does not bind companion period")
    if not isinstance(companion.unit, str) or companion.unit.strip() != companion.unit or not companion.unit:
        raise AttestedQuerySnapshotError("Company Facts companion unit label is invalid")
    unit_parts = companion.unit.split("/")
    if len(unit_parts) == 2 and all(part.strip() for part in unit_parts):
        expected_measures = (unit_parts[0].strip(),)
        expected_denominator = (unit_parts[1].strip(),)
    else:
        expected_measures = (companion.unit,)
        expected_denominator = ()
    expected_unit_id = stable_id("sec_companyfacts_unit", expected_measures, expected_denominator)
    if (
        occurrence.unit is None
        or occurrence.unit.unit_id != expected_unit_id
        or occurrence.unit.measures != expected_measures
        or occurrence.unit.denominator_measures != expected_denominator
    ):
        raise AttestedQuerySnapshotError("Company Facts occurrence unit does not bind companion unit")
    if match.get("taxonomy") != companion.taxonomy or match.get("concept") != companion.concept or match.get("unit") != companion.unit or match.get("entry_index") != companion.entry_index:
        raise AttestedQuerySnapshotError("Company Facts binding does not match B3 taxonomy/concept/unit/entry")
    projection = match.get("projection")
    if not isinstance(projection, Mapping):
        raise AttestedQuerySnapshotError("B3 Company Facts match projection is invalid")
    if projection.get("cik") != occurrence.source.entity_id or projection.get("accession") != occurrence.source.accession:
        raise AttestedQuerySnapshotError("B3 Company Facts projection does not bind occurrence identity")
    if projection.get("start") != start or projection.get("end") != end:
        raise AttestedQuerySnapshotError("B3 Company Facts projection period does not bind occurrence")
    if decimal_text(occurrence.parsed_value) != projection.get("value"):
        raise AttestedQuerySnapshotError("B3 Company Facts projection value does not bind occurrence")
    if occurrence.is_nil or occurrence.parsed_value is None:
        raise AttestedQuerySnapshotError("nil or value-less Company Facts occurrence cannot carry an attested match")
    return {
        "capture_id": cf["capture_id"], "manifest_id": cf["manifest_id"], "response_sha256": cf["response_sha256"],
        "cik": occurrence.source.entity_id, "accession": occurrence.source.accession,
        "taxonomy": companion.taxonomy, "concept": companion.concept, "unit": companion.unit,
        "entry_index": companion.entry_index, "start": start, "end": end,
        "value": decimal_text(occurrence.parsed_value), "dimensions_known": False,
    }


def _eligible_leaf_ids(base: QuerySnapshot) -> set[str]:
    """Return leaves intrinsically eligible for B4, independent of coverage."""
    selected, _ = _selected_raw_occurrences(base)
    return {
        occurrence_id
        for occurrence_id, occurrence in selected.items()
        if occurrence.source.source == "sec-companyfacts"
        and occurrence.dimensions_known is False
    }


def _validated_bindings(
    *, base: QuerySnapshot, conversion: CompanyFactsLedgerConversion, records: Mapping[str, Mapping[str, Any]], bindings: Sequence[AttestedOccurrenceBinding]
) -> tuple[list[dict[str, Any]], dict[str, tuple[str, ...]]]:
    if type(conversion) is not CompanyFactsLedgerConversion:
        raise AttestedQuerySnapshotError("companyfacts_conversion must be an exact CompanyFactsLedgerConversion")
    try:
        conversion.__post_init__()
    except (TypeError, ValueError) as exc:
        raise AttestedQuerySnapshotError(f"Company Facts conversion invariant failed: {exc}") from exc
    if type(bindings) is not tuple or not bindings or len(bindings) > HARD_MAX_ATTESTED_SNAPSHOT_BINDINGS:
        raise AttestedQuerySnapshotError("occurrence_bindings must be a non-empty bounded tuple")
    if {item.attestation_id for item in bindings if type(item) is AttestedOccurrenceBinding} != set(records):
        raise AttestedQuerySnapshotError("every stored attestation must be used by at least one explicit occurrence binding")
    selected, roots = _selected_raw_occurrences(base)
    companions = {item.occurrence.occurrence_id: item for item in conversion.occurrences}
    seen_occurrences: set[str] = set()
    seen_matches: set[tuple[str, str]] = set()
    prepared: list[dict[str, Any]] = []
    for binding in bindings:
        if type(binding) is not AttestedOccurrenceBinding:
            raise AttestedQuerySnapshotError("occurrence bindings must be exact AttestedOccurrenceBinding values")
        if binding.occurrence_id in seen_occurrences:
            raise AttestedQuerySnapshotError("occurrence bindings cannot choose an occurrence twice")
        record = records.get(binding.attestation_id)
        occurrence = selected.get(binding.occurrence_id)
        companion = companions.get(binding.occurrence_id)
        if record is None or occurrence is None or companion is None:
            raise AttestedQuerySnapshotError("occurrence binding does not name a selected converted occurrence and supplied attestation")
        receipt = conversion.receipt
        cf = record["company_facts"]
        if (
            receipt.capture_id != cf["capture_id"]
            or receipt.manifest_id != cf["manifest_id"]
            or receipt.cik != record["filing"]["cik"]
        ):
            raise AttestedQuerySnapshotError("Company Facts conversion receipt does not bind attestation capture")
        matches = {item["match_id"]: item for item in cf["matches"]}
        match = matches.get(binding.match_id)
        if match is None or (binding.attestation_id, binding.match_id) in seen_matches:
            raise AttestedQuerySnapshotError("occurrence binding Company Facts match is missing or reused")
        projection = _binding_projection(occurrence=occurrence, companion=companion, attestation=record, match=match)
        prepared.append({**binding.to_dict(), "companyfacts": projection})
        seen_occurrences.add(binding.occurrence_id)
        seen_matches.add((binding.attestation_id, binding.match_id))
    prepared.sort(key=lambda item: item["occurrence_id"])
    return prepared, roots


def _coverage_rows(roots: Mapping[str, tuple[str, ...]], bindings: Sequence[Mapping[str, Any]], eligible_ids: set[str]) -> list[dict[str, Any]]:
    bound_ids = {item["occurrence_id"] for item in bindings}
    rows: list[dict[str, Any]] = []
    for root_cell_id in sorted(roots):
        leaves = roots[root_cell_id]
        eligible = tuple(item for item in leaves if item in eligible_ids)
        attested = tuple(item for item in leaves if item in bound_ids)
        if not leaves or not eligible:
            status = "not_evaluable"
        elif len(attested) == len(leaves) and len(eligible) == len(leaves):
            status = "all_leaves_attested"
        elif attested:
            status = "partially_attested"
        else:
            status = "not_attested"
        rows.append({"root_cell_id": root_cell_id, "selected_leaf_occurrence_ids": list(leaves), "eligible_leaf_occurrence_ids": list(eligible), "attested_occurrence_ids": list(attested), "status": status})
    return rows


def _attestation_projection(record: Mapping[str, Any]) -> dict[str, Any]:
    cf = record["company_facts"]
    return {
        "attestation_id": record["attestation_id"],
        "authority_snapshot_id": record["authority"]["snapshot_id"],
        "package_id": record["package"]["package_id"],
        "extraction_id": record["extraction"]["extraction_id"],
        "cik": record["filing"]["cik"],
        "accession": record["filing"]["accession"],
        "companyfacts_capture_id": cf["capture_id"],
        "companyfacts_manifest_id": cf["manifest_id"],
        "companyfacts_response_sha256": cf["response_sha256"],
        "companyfacts_match_count": len(cf["matches"]),
        "attested_at": record["clocks"]["attested_at"],
    }


def _base_projection(base: QuerySnapshot) -> dict[str, Any]:
    manifest_payload = canonical_json(dict(base.manifest)).encode("utf-8")
    objects = []
    for item in base.manifest["objects"]:
        objects.append({
            "role": item["role"], "object_key": item["object_key"], "sha256": item["sha256"],
            "byte_length": item["byte_length"], "content_type": item["content_type"],
        })
    return {
        "snapshot_id": base.snapshot_id,
        "query_hash": base.matrix.query_hash,
        "manifest_key": base.manifest_key,
        "manifest_sha256": sha256(manifest_payload).hexdigest(),
        "manifest_byte_length": len(manifest_payload),
        "objects": objects,
    }


def _coverage_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = {status: 0 for status in ("all_leaves_attested", "partially_attested", "not_attested", "not_evaluable")}
    for row in rows:
        counts[row["status"]] += 1
    return {
        "coverage_scope": "selected_raw_fact_leaves_only",
        "positive_label": "B3_selected_member_companyfacts_row_correspondence_only",
        "root_cell_count": len(rows),
        **counts,
    }


def _validate_conversion_receipt_projection(value: Any) -> None:
    required = frozenset({
        "receipt_id", "schema", "adapter_version", "capture_id", "manifest_id", "cik", "clocks",
        "submissions_clock_scope", "input_sha256", "companyfacts_sha256", "submissions_sha256", "output_sha256",
        "submission_sources", "occurrence_count", "output_occurrence_count", "submission_row_count",
        "older_submissions_file_count", "mapped_accessions", "unmapped_accessions", "mapped_accession_count",
        "unmapped_accession_count", "pit_eligible_count", "typed_revision_count", "availability",
    })
    receipt = _strict_object(value, field="Company Facts conversion receipt", required=required)
    if receipt["schema"] != "fundamental_forensics.companyfacts_ledger_receipt/v2" or not isinstance(receipt["receipt_id"], str) or not re.fullmatch(r"cffledger_[a-f0-9]{64}", receipt["receipt_id"]):
        raise AttestedQuerySnapshotError("Company Facts conversion receipt identity is invalid")
    for key in ("input_sha256", "companyfacts_sha256", "submissions_sha256", "output_sha256"):
        if not isinstance(receipt[key], str) or not _SHA_RE.fullmatch(receipt[key]):
            raise AttestedQuerySnapshotError("Company Facts conversion receipt digest is invalid")
    if not isinstance(receipt["clocks"], Mapping) or tuple(receipt["clocks"]) != ("acquisition_started_at", "captured_at", "recorded_at", "source_snapshot_at", "submissions_recorded_at"):
        raise AttestedQuerySnapshotError("Company Facts conversion receipt clocks are invalid")
    for key, clock in receipt["clocks"].items():
        if utc_text(_utc(clock, field=f"Company Facts receipt {key}")) != clock:
            raise AttestedQuerySnapshotError("Company Facts conversion receipt clocks are not canonical")
    integer_names = (
        "occurrence_count", "output_occurrence_count", "submission_row_count", "older_submissions_file_count",
        "mapped_accession_count", "unmapped_accession_count", "pit_eligible_count", "typed_revision_count",
    )
    if any(isinstance(receipt[key], bool) or not isinstance(receipt[key], int) or receipt[key] < 0 for key in integer_names):
        raise AttestedQuerySnapshotError("Company Facts conversion receipt counts are invalid")
    if receipt["occurrence_count"] != receipt["output_occurrence_count"] or receipt["availability"] not in {"available", "partial"}:
        raise AttestedQuerySnapshotError("Company Facts conversion receipt summary is invalid")
    if any(type(receipt[key]) not in _JSON_SEQUENCE_TYPES for key in ("submission_sources", "mapped_accessions", "unmapped_accessions")):
        raise AttestedQuerySnapshotError("Company Facts conversion receipt collections are invalid")


def _manifest_body(*, base: QuerySnapshot, records: Mapping[str, Mapping[str, Any]], coverage_rows: Sequence[Mapping[str, Any]], conversion: CompanyFactsLedgerConversion, artifacts: Sequence[AttestedQuerySnapshotArtifact], operator_verification_observed_at: str, published_at: str) -> dict[str, Any]:
    return {
        "schema": ATTESTED_QUERY_SNAPSHOT_SCHEMA,
        "prefix": ATTESTED_QUERY_SNAPSHOT_PREFIX,
        "base_snapshot": _base_projection(base),
        "policy": {
            "version": ATTESTED_QUERY_SNAPSHOT_POLICY_VERSION,
            "fingerprint": ATTESTED_QUERY_SNAPSHOT_POLICY_FINGERPRINT,
        },
        "companyfacts_conversion_receipt": conversion.receipt.to_dict(),
        "attestation_projections": [_attestation_projection(records[key]) for key in sorted(records)],
        "coverage_summary": _coverage_summary(coverage_rows),
        "clocks": {
            "query_source_snapshot_at": base.manifest["clocks"]["source_snapshot_at"],
            "query_recorded_at": base.manifest["clocks"]["recorded_at"],
            "query_computed_at": base.manifest["clocks"]["computed_at"],
            "query_published_at": base.manifest["clocks"]["published_at"],
            "operator_verification_observed_at": operator_verification_observed_at,
            "published_at": published_at,
        },
        "nonclaims": {
            "filing_complete": False,
            "taxonomy_validation_complete": False,
            "relationship_validation_complete": False,
            "calculation_validation_complete": False,
            "companyfacts_completeness": False,
            "fact_level_xbrl_identity": False,
            "dimensions_known": False,
            "signature_verified": False,
            "trading_authority": False,
            "query_snapshot_complete": False,
            "companyfacts_capture_complete": False,
            "filing_source_snapshot_complete": False,
            "sec_universe_complete": False,
            "pit_or_contemporaneous_verification": False,
            "current_source_available_or_fresh": False,
            "accounting_correctness": False,
            "restatement_correctness": False,
            "audit_opinion_authority": False,
            "prophet_authority": False,
            "neural_web_authority": False,
            "investment_or_legal_authority": False,
            "trusted_timestamp_authority": False,
            "verification_time_cryptographically_attested": False,
        },
        "objects": [item.to_dict() for item in artifacts],
    }


def _identity(body: Mapping[str, Any]) -> str:
    return ATTESTED_QUERY_SNAPSHOT_ID_PREFIX + sha256(canonical_json(dict(body)).encode("utf-8")).hexdigest()


def _validate_manifest(manifest: Mapping[str, Any]) -> None:
    required = frozenset({"schema", "prefix", "snapshot_id", "base_snapshot", "policy", "companyfacts_conversion_receipt", "attestation_projections", "coverage_summary", "clocks", "nonclaims", "objects"})
    item = _strict_object(manifest, field="attested query snapshot manifest", required=required)
    if item["schema"] != ATTESTED_QUERY_SNAPSHOT_SCHEMA or item["prefix"] != ATTESTED_QUERY_SNAPSHOT_PREFIX:
        raise AttestedQuerySnapshotError("unsupported attested snapshot manifest")
    snapshot_id = _snapshot_id(item["snapshot_id"])
    base = _strict_object(item["base_snapshot"], field="attested snapshot base binding", required=frozenset({"snapshot_id", "query_hash", "manifest_key", "manifest_sha256", "manifest_byte_length", "objects"}))
    _v1_snapshot_id(base["snapshot_id"])
    if not isinstance(base["query_hash"], str) or not _SHA_RE.fullmatch(base["query_hash"]) or base["manifest_key"] != _v1_manifest_key(base["snapshot_id"]) or not isinstance(base["manifest_sha256"], str) or not _SHA_RE.fullmatch(base["manifest_sha256"]) or isinstance(base["manifest_byte_length"], bool) or not isinstance(base["manifest_byte_length"], int) or base["manifest_byte_length"] < 0 or base["manifest_byte_length"] > HARD_MAX_SNAPSHOT_MANIFEST_BYTES:
        raise AttestedQuerySnapshotError("attested snapshot base binding is invalid")
    if type(base["objects"]) not in _JSON_SEQUENCE_TYPES or len(base["objects"]) != len(_V1_ROLE_LIMITS):
        raise AttestedQuerySnapshotError("attested snapshot base object binding is invalid")
    base_roles: list[str] = []
    for raw_object in base["objects"]:
        current = _strict_object(raw_object, field="attested snapshot base object", required=frozenset({"role", "object_key", "sha256", "byte_length", "content_type"}))
        role = current["role"]
        if role not in _V1_ROLE_LIMITS or not isinstance(current["object_key"], str) or not isinstance(current["sha256"], str) or not _SHA_RE.fullmatch(current["sha256"]) or isinstance(current["byte_length"], bool) or not isinstance(current["byte_length"], int) or not 0 <= current["byte_length"] <= _V1_ROLE_LIMITS[role]:
            raise AttestedQuerySnapshotError("attested snapshot base object binding is invalid")
        base_roles.append(role)
    if base_roles != list(_V1_ROLE_LIMITS):
        raise AttestedQuerySnapshotError("attested snapshot base object binding is not canonical")
    policy = _strict_object(item["policy"], field="attested snapshot policy", required=frozenset({"version", "fingerprint"}))
    if policy["version"] != ATTESTED_QUERY_SNAPSHOT_POLICY_VERSION or policy["fingerprint"] != ATTESTED_QUERY_SNAPSHOT_POLICY_FINGERPRINT:
        raise AttestedQuerySnapshotError("attested snapshot policy is unsupported")
    receipt = item["companyfacts_conversion_receipt"]
    _validate_conversion_receipt_projection(receipt)
    if type(item["attestation_projections"]) not in _JSON_SEQUENCE_TYPES or not item["attestation_projections"] or len(item["attestation_projections"]) > HARD_MAX_ATTESTED_SNAPSHOT_ATTESTATIONS:
        raise AttestedQuerySnapshotError("attested snapshot attestation projections are invalid")
    projections = item["attestation_projections"]
    names: list[str] = []
    for projection in projections:
        expected = frozenset({"attestation_id", "authority_snapshot_id", "package_id", "extraction_id", "cik", "accession", "companyfacts_capture_id", "companyfacts_manifest_id", "companyfacts_response_sha256", "companyfacts_match_count", "attested_at"})
        current = _strict_object(projection, field="attested snapshot projection", required=expected)
        if not isinstance(current["attestation_id"], str) or not _ATTESTATION_ID_RE.fullmatch(current["attestation_id"]):
            raise AttestedQuerySnapshotError("attested snapshot projection id is invalid")
        if not isinstance(current["companyfacts_response_sha256"], str) or not _SHA_RE.fullmatch(current["companyfacts_response_sha256"]):
            raise AttestedQuerySnapshotError("attested snapshot projection Company Facts SHA is invalid")
        if isinstance(current["companyfacts_match_count"], bool) or not isinstance(current["companyfacts_match_count"], int) or current["companyfacts_match_count"] <= 0:
            raise AttestedQuerySnapshotError("attested snapshot projection match count is invalid")
        _utc(current["attested_at"], field="attestation projection attested_at")
        names.append(current["attestation_id"])
    if names != sorted(names) or len(set(names)) != len(names):
        raise AttestedQuerySnapshotError("attested snapshot projections are not canonical")
    summary = _strict_object(item["coverage_summary"], field="attested snapshot coverage summary", required=frozenset({"coverage_scope", "positive_label", "root_cell_count", "all_leaves_attested", "partially_attested", "not_attested", "not_evaluable"}))
    if summary["coverage_scope"] != "selected_raw_fact_leaves_only" or summary["positive_label"] != "B3_selected_member_companyfacts_row_correspondence_only":
        raise AttestedQuerySnapshotError("attested snapshot coverage summary labels are invalid")
    if any(isinstance(summary[key], bool) or not isinstance(summary[key], int) or summary[key] < 0 for key in ("root_cell_count", "all_leaves_attested", "partially_attested", "not_attested", "not_evaluable")) or summary["root_cell_count"] != sum(summary[key] for key in ("all_leaves_attested", "partially_attested", "not_attested", "not_evaluable")) or summary["root_cell_count"] > HARD_MAX_ATTESTED_SNAPSHOT_ROOT_CELLS:
        raise AttestedQuerySnapshotError("attested snapshot coverage summary counts are invalid")
    clocks = _strict_object(item["clocks"], field="attested snapshot clocks", required=frozenset({"query_source_snapshot_at", "query_recorded_at", "query_computed_at", "query_published_at", "operator_verification_observed_at", "published_at"}))
    parsed = {key: _utc(value, field=f"attested snapshot {key}") for key, value in clocks.items()}
    if any(utc_text(parsed[key]) != clocks[key] for key in parsed):
        raise AttestedQuerySnapshotError("attested snapshot clocks are not canonical UTC")
    if parsed["query_computed_at"] < max(parsed["query_source_snapshot_at"], parsed["query_recorded_at"]) or parsed["query_published_at"] < parsed["query_computed_at"] or parsed["operator_verification_observed_at"] < parsed["query_published_at"] or parsed["published_at"] < parsed["operator_verification_observed_at"]:
        raise AttestedQuerySnapshotError("attested snapshot clock ordering is invalid")
    nonclaims = _strict_object(item["nonclaims"], field="attested snapshot nonclaims", required=frozenset({"filing_complete", "taxonomy_validation_complete", "relationship_validation_complete", "calculation_validation_complete", "companyfacts_completeness", "fact_level_xbrl_identity", "dimensions_known", "signature_verified", "trading_authority", "query_snapshot_complete", "companyfacts_capture_complete", "filing_source_snapshot_complete", "sec_universe_complete", "pit_or_contemporaneous_verification", "current_source_available_or_fresh", "accounting_correctness", "restatement_correctness", "audit_opinion_authority", "prophet_authority", "neural_web_authority", "investment_or_legal_authority", "trusted_timestamp_authority", "verification_time_cryptographically_attested"}))
    if any(value is not False for value in nonclaims.values()):
        raise AttestedQuerySnapshotError("attested snapshot nonclaims must remain false")
    if type(item["objects"]) not in _JSON_SEQUENCE_TYPES or len(item["objects"]) != len(_ROLES):
        raise AttestedQuerySnapshotError("attested snapshot object count is invalid")
    artifacts: list[AttestedQuerySnapshotArtifact] = []
    for raw in item["objects"]:
        artifacts.append(AttestedQuerySnapshotArtifact(**_strict_object(raw, field="attested snapshot object", required=frozenset({"role", "object_key", "sha256", "byte_length", "content_type"}))))
    if tuple(value.role for value in artifacts) != _ROLES or len({value.object_key for value in artifacts}) != len(artifacts) or sum(value.byte_length for value in artifacts) > HARD_MAX_ATTESTED_SNAPSHOT_TOTAL_BYTES:
        raise AttestedQuerySnapshotError("attested snapshot objects are invalid")
    body = dict(item); body.pop("snapshot_id")
    if snapshot_id != _identity(body):
        raise AttestedQuerySnapshotError("attested snapshot identity mismatch")


def _manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    _validate_manifest(manifest)
    return _canonical_payload(manifest, field="attested snapshot manifest", limit=HARD_MAX_ATTESTED_SNAPSHOT_MANIFEST_BYTES)


def _decode_manifest(payload: bytes) -> dict[str, Any]:
    manifest = _json_object(payload, field="attested query snapshot manifest", limit=HARD_MAX_ATTESTED_SNAPSHOT_MANIFEST_BYTES)
    _validate_manifest(manifest)
    if _manifest_bytes(manifest) != payload:
        raise AttestedQuerySnapshotError("attested query snapshot manifest is not canonical")
    return manifest


_ATTESTATIONS_PAYLOAD_SCHEMA = "fundamental_forensics.attested_query_snapshot_attestations/v2"
_CONVERSION_PAYLOAD_SCHEMA = "fundamental_forensics.attested_query_snapshot_companyfacts_conversion/v2"
_BINDINGS_PAYLOAD_SCHEMA = "fundamental_forensics.attested_query_snapshot_bindings/v2"
_COVERAGE_PAYLOAD_SCHEMA = "fundamental_forensics.attested_query_snapshot_coverage/v2"


def _attestations_payload(records: Mapping[str, Mapping[str, Any]]) -> bytes:
    items = [{"attestation_id": key, "record": records[key]} for key in sorted(records)]
    return _canonical_payload({"schema": _ATTESTATIONS_PAYLOAD_SCHEMA, "items": items}, field="attestations payload", limit=HARD_MAX_ATTESTED_SNAPSHOT_ATTESTATIONS_BYTES)


def _decode_attestations(payload: bytes, projections: Sequence[Mapping[str, Any]]) -> Mapping[str, Mapping[str, Any]]:
    raw = _json_object(payload, field="attestations payload", limit=HARD_MAX_ATTESTED_SNAPSHOT_ATTESTATIONS_BYTES)
    value = _strict_object(raw, field="attestations payload", required=frozenset({"schema", "items"}))
    if value["schema"] != _ATTESTATIONS_PAYLOAD_SCHEMA or not isinstance(value["items"], list) or not value["items"] or len(value["items"]) > HARD_MAX_ATTESTED_SNAPSHOT_ATTESTATIONS:
        raise AttestedQuerySnapshotError("attestations payload is invalid")
    out: dict[str, Mapping[str, Any]] = {}
    expected_items: list[dict[str, Any]] = []
    for item in value["items"]:
        parsed = _strict_object(item, field="attestation payload item", required=frozenset({"attestation_id", "record"}))
        if not isinstance(parsed["record"], Mapping):
            raise AttestedQuerySnapshotError("attestation payload record is invalid")
        try:
            record = FilingAttestation.from_dict(parsed["record"]).to_dict()
        except (FilingAttestationError, TypeError, ValueError) as exc:
            raise AttestedQuerySnapshotError(f"stored B3 attestation is invalid: {exc}") from exc
        if parsed["attestation_id"] != record["attestation_id"] or record["attestation_id"] in out:
            raise AttestedQuerySnapshotError("attestation payload identity is invalid")
        if record["company_facts"]["requested"] is not True or not record["company_facts"]["matches"]:
            raise AttestedQuerySnapshotError("attestation payload lacks a positive B3 Company Facts projection")
        out[record["attestation_id"]] = _freeze(record)
        expected_items.append({"attestation_id": record["attestation_id"], "record": record})
    if [item["attestation_id"] for item in expected_items] != sorted(out):
        raise AttestedQuerySnapshotError("attestation payload is not canonically ordered")
    if _canonical_payload({"schema": _ATTESTATIONS_PAYLOAD_SCHEMA, "items": expected_items}, field="attestations payload", limit=HARD_MAX_ATTESTED_SNAPSHOT_ATTESTATIONS_BYTES) != payload:
        raise AttestedQuerySnapshotError("attestations payload is not canonical")
    actual_projections = [_attestation_projection(out[key]) for key in sorted(out)]
    if actual_projections != list(projections):
        raise AttestedQuerySnapshotError("attestation payload does not match manifest projections")
    return MappingProxyType(out)


def _conversion_payload(conversion: CompanyFactsLedgerConversion) -> bytes:
    try:
        conversion.__post_init__()
    except (TypeError, ValueError) as exc:
        raise AttestedQuerySnapshotError(f"Company Facts conversion invariant failed: {exc}") from exc
    value = {
        "schema": _CONVERSION_PAYLOAD_SCHEMA,
        "ledger": conversion.ledger.to_dict(),
        "occurrences": [item.to_dict() for item in conversion.occurrences],
        "submission_sources": [item.to_dict() for item in conversion.submission_sources],
        "receipt": conversion.receipt.to_dict(),
    }
    return _canonical_payload(value, field="Company Facts conversion payload", limit=HARD_MAX_ATTESTED_SNAPSHOT_CONVERSION_BYTES, maximum_nodes=HARD_MAX_ATTESTED_CONVERSION_JSON_NODES)


def _receipt_from_dict(value: Any) -> CompanyFactsLedgerReceipt:
    _validate_conversion_receipt_projection(value)
    raw = _strict_object(value, field="Company Facts conversion receipt", required=frozenset({
        "receipt_id", "schema", "adapter_version", "capture_id", "manifest_id", "cik", "clocks",
        "submissions_clock_scope", "input_sha256", "companyfacts_sha256", "submissions_sha256", "output_sha256",
        "submission_sources", "occurrence_count", "output_occurrence_count", "submission_row_count",
        "older_submissions_file_count", "mapped_accessions", "unmapped_accessions", "mapped_accession_count",
        "unmapped_accession_count", "pit_eligible_count", "typed_revision_count", "availability",
    }))
    try:
        witnesses = tuple(SubmissionSourceWitness(**_strict_object(item, field="Company Facts submission witness", required=frozenset({"source_name", "payload_sha256", "row_count", "is_older"}))) for item in raw["submission_sources"])
        receipt = CompanyFactsLedgerReceipt(
            receipt_id=raw["receipt_id"], schema=raw["schema"], adapter_version=raw["adapter_version"],
            capture_id=raw["capture_id"], manifest_id=raw["manifest_id"], cik=raw["cik"],
            clocks=tuple((key, raw["clocks"][key]) for key in ("acquisition_started_at", "captured_at", "recorded_at", "source_snapshot_at", "submissions_recorded_at")),
            submissions_clock_scope=raw["submissions_clock_scope"], input_sha256=raw["input_sha256"],
            companyfacts_sha256=raw["companyfacts_sha256"], submissions_sha256=raw["submissions_sha256"],
            output_sha256=raw["output_sha256"], submission_sources=witnesses,
            occurrence_count=raw["occurrence_count"], output_occurrence_count=raw["output_occurrence_count"],
            submission_row_count=raw["submission_row_count"], older_submissions_file_count=raw["older_submissions_file_count"],
            mapped_accessions=tuple(raw["mapped_accessions"]), unmapped_accessions=tuple(raw["unmapped_accessions"]),
            mapped_accession_count=raw["mapped_accession_count"], unmapped_accession_count=raw["unmapped_accession_count"],
            pit_eligible_count=raw["pit_eligible_count"], typed_revision_count=raw["typed_revision_count"], availability=raw["availability"],
        )
    except (TypeError, ValueError) as exc:
        raise AttestedQuerySnapshotError(f"stored Company Facts conversion receipt is invalid: {exc}") from exc
    if receipt.to_dict() != _thaw(raw):
        raise AttestedQuerySnapshotError("stored Company Facts conversion receipt is not canonical")
    return receipt


def _decode_conversion(payload: bytes, receipt_projection: Mapping[str, Any]) -> CompanyFactsLedgerConversion:
    raw = _json_object(payload, field="Company Facts conversion payload", limit=HARD_MAX_ATTESTED_SNAPSHOT_CONVERSION_BYTES, maximum_nodes=HARD_MAX_ATTESTED_CONVERSION_JSON_NODES)
    value = _strict_object(raw, field="Company Facts conversion payload", required=frozenset({"schema", "ledger", "occurrences", "submission_sources", "receipt"}))
    if value["schema"] != _CONVERSION_PAYLOAD_SCHEMA or not isinstance(value["ledger"], dict) or not isinstance(value["occurrences"], list) or not isinstance(value["submission_sources"], list):
        raise AttestedQuerySnapshotError("Company Facts conversion payload is invalid")
    receipt = _receipt_from_dict(value["receipt"])
    if receipt.to_dict() != _thaw(receipt_projection):
        raise AttestedQuerySnapshotError("Company Facts conversion payload receipt does not match manifest")
    try:
        # Re-enter through the ledger's strict canonical wire decoder.  The
        # outer B4 payload is already bounded JSON, but this keeps the nested
        # ledger on its own public hostile-input contract as well.
        ledger = RawFactLedger.from_json_bytes(
            canonical_json(value["ledger"]).encode("utf-8")
        )
        by_id = {item.occurrence_id: item for item in ledger.events}
        companions: list[CompanyFactsLedgerOccurrence] = []
        for item in value["occurrences"]:
            parsed = _strict_object(item, field="Company Facts conversion companion", required=frozenset({"occurrence_id", "taxonomy", "concept", "unit", "entry_index", "start", "end", "fy", "fp", "frame", "form", "filed", "accn", "pit_eligible", "availability", "amendment_declared", "revision_evidence_id", "revision_evidence_available_at", "event_type", "revision_of"}))
            occurrence = by_id.get(parsed["occurrence_id"])
            if occurrence is None or parsed["event_type"] != occurrence.event_type.value or parsed["revision_of"] != occurrence.revision_of:
                raise AttestedQuerySnapshotError("Company Facts conversion companion does not bind ledger occurrence")
            companions.append(CompanyFactsLedgerOccurrence(
                occurrence=occurrence, taxonomy=parsed["taxonomy"], concept=parsed["concept"], unit=parsed["unit"], entry_index=parsed["entry_index"],
                start=parsed["start"], end=parsed["end"], fy=parsed["fy"], fp=parsed["fp"], frame=parsed["frame"], form=parsed["form"], filed=parsed["filed"],
                accession=parsed["accn"], pit_eligible=parsed["pit_eligible"], availability=AvailabilityStatus(parsed["availability"]), amendment_declared=parsed["amendment_declared"],
                revision_evidence_id=parsed["revision_evidence_id"], revision_evidence_available_at=parsed["revision_evidence_available_at"],
            ))
        sources = tuple(SubmissionSourceWitness(**_strict_object(item, field="Company Facts conversion source", required=frozenset({"source_name", "payload_sha256", "row_count", "is_older"}))) for item in value["submission_sources"])
        conversion = CompanyFactsLedgerConversion(ledger=ledger, occurrences=tuple(companions), submission_sources=sources, receipt=receipt)
    except AttestedQuerySnapshotError:
        raise
    except (TypeError, ValueError) as exc:
        raise AttestedQuerySnapshotError(f"stored Company Facts conversion is invalid: {exc}") from exc
    expected = _conversion_payload(conversion)
    if expected != payload:
        raise AttestedQuerySnapshotError("Company Facts conversion payload is not canonical")
    return conversion


def _binding_payload(bindings: Sequence[Mapping[str, Any]]) -> bytes:
    return _canonical_payload({"schema": _BINDINGS_PAYLOAD_SCHEMA, "items": list(bindings)}, field="bindings payload", limit=HARD_MAX_ATTESTED_SNAPSHOT_BINDINGS_BYTES)


def _binding_from_payload(item: Mapping[str, Any], records: Mapping[str, Mapping[str, Any]]) -> tuple[AttestedOccurrenceBinding, dict[str, Any]]:
    raw = _strict_object(item, field="attested occurrence binding", required=frozenset({"occurrence_id", "attestation_id", "match_id", "companyfacts"}))
    binding = AttestedOccurrenceBinding(raw["occurrence_id"], raw["attestation_id"], raw["match_id"])
    record = records.get(binding.attestation_id)
    if record is None:
        raise AttestedQuerySnapshotError("binding references an unrecorded attestation")
    companyfacts = _strict_object(raw["companyfacts"], field="attested occurrence Company Facts projection", required=frozenset({"capture_id", "manifest_id", "response_sha256", "cik", "accession", "taxonomy", "concept", "unit", "entry_index", "start", "end", "value", "dimensions_known"}))
    if companyfacts["dimensions_known"] is not False:
        raise AttestedQuerySnapshotError("binding must preserve dimensions_known=false")
    if not isinstance(companyfacts["response_sha256"], str) or not _SHA_RE.fullmatch(companyfacts["response_sha256"]):
        raise AttestedQuerySnapshotError("binding Company Facts response SHA is invalid")
    if isinstance(companyfacts["entry_index"], bool) or not isinstance(companyfacts["entry_index"], int) or companyfacts["entry_index"] < 0:
        raise AttestedQuerySnapshotError("binding Company Facts entry index is invalid")
    _date_text(companyfacts["start"], field="binding.start", nullable=True)
    _date_text(companyfacts["end"], field="binding.end")
    if not isinstance(companyfacts["value"], str) or decimal_text(companyfacts["value"]) != companyfacts["value"]:
        raise AttestedQuerySnapshotError("binding Company Facts value is not canonical")
    cf = record["company_facts"]
    if any(companyfacts[field] != cf[field] for field in ("capture_id", "manifest_id", "response_sha256")):
        raise AttestedQuerySnapshotError("binding Company Facts capture does not match attestation")
    match = next((match for match in cf["matches"] if match["match_id"] == binding.match_id), None)
    if match is None:
        raise AttestedQuerySnapshotError("binding match is absent from B3 attestation")
    projection = match["projection"]
    if (
        companyfacts["taxonomy"] != match["taxonomy"]
        or companyfacts["concept"] != match["concept"]
        or companyfacts["unit"] != match["unit"]
        or companyfacts["entry_index"] != match["entry_index"]
        or any(companyfacts[field] != projection[field] for field in ("cik", "accession", "start", "end", "value"))
    ):
        raise AttestedQuerySnapshotError("binding Company Facts projection does not match B3 correspondence")
    return binding, {**binding.to_dict(), "companyfacts": companyfacts}


def _decode_bindings(payload: bytes, records: Mapping[str, Mapping[str, Any]]) -> tuple[tuple[AttestedOccurrenceBinding, ...], tuple[Mapping[str, Any], ...]]:
    raw = _json_object(payload, field="bindings payload", limit=HARD_MAX_ATTESTED_SNAPSHOT_BINDINGS_BYTES)
    value = _strict_object(raw, field="bindings payload", required=frozenset({"schema", "items"}))
    if value["schema"] != _BINDINGS_PAYLOAD_SCHEMA or not isinstance(value["items"], list) or not value["items"] or len(value["items"]) > HARD_MAX_ATTESTED_SNAPSHOT_BINDINGS:
        raise AttestedQuerySnapshotError("bindings payload is invalid")
    bindings: list[AttestedOccurrenceBinding] = []
    normalized: list[Mapping[str, Any]] = []
    used_occurrences: set[str] = set()
    used_matches: set[tuple[str, str]] = set()
    for item in value["items"]:
        if not isinstance(item, Mapping):
            raise AttestedQuerySnapshotError("bindings payload item is invalid")
        binding, projection = _binding_from_payload(item, records)
        if binding.occurrence_id in used_occurrences or (binding.attestation_id, binding.match_id) in used_matches:
            raise AttestedQuerySnapshotError("bindings payload reuses an occurrence or B3 match")
        bindings.append(binding); normalized.append(projection)
        used_occurrences.add(binding.occurrence_id); used_matches.add((binding.attestation_id, binding.match_id))
    if [item.occurrence_id for item in bindings] != sorted(item.occurrence_id for item in bindings):
        raise AttestedQuerySnapshotError("bindings payload is not canonically ordered")
    expected = _binding_payload(normalized)
    if expected != payload:
        raise AttestedQuerySnapshotError("bindings payload is not canonical")
    return tuple(bindings), tuple(_freeze(item) for item in normalized)


def _coverage_payload(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return _canonical_payload({"schema": _COVERAGE_PAYLOAD_SCHEMA, "items": list(rows)}, field="coverage payload", limit=HARD_MAX_ATTESTED_SNAPSHOT_COVERAGE_BYTES)


def _decode_coverage(payload: bytes, *, base: QuerySnapshot, conversion: CompanyFactsLedgerConversion, bindings: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    raw = _json_object(payload, field="coverage payload", limit=HARD_MAX_ATTESTED_SNAPSHOT_COVERAGE_BYTES)
    value = _strict_object(raw, field="coverage payload", required=frozenset({"schema", "items"}))
    if value["schema"] != _COVERAGE_PAYLOAD_SCHEMA or not isinstance(value["items"], list) or len(value["items"]) > HARD_MAX_ATTESTED_SNAPSHOT_ROOT_CELLS:
        raise AttestedQuerySnapshotError("coverage payload is invalid")
    _, roots = _selected_raw_occurrences(base)
    expected = _coverage_rows(roots, bindings, _eligible_leaf_ids(base))
    normalized: list[dict[str, Any]] = []
    for item in value["items"]:
        parsed = _strict_object(item, field="root cell coverage", required=frozenset({"root_cell_id", "selected_leaf_occurrence_ids", "eligible_leaf_occurrence_ids", "attested_occurrence_ids", "status"}))
        if not isinstance(parsed["root_cell_id"], str) or not isinstance(parsed["selected_leaf_occurrence_ids"], list) or not isinstance(parsed["eligible_leaf_occurrence_ids"], list) or not isinstance(parsed["attested_occurrence_ids"], list) or parsed["status"] not in {"all_leaves_attested", "partially_attested", "not_attested", "not_evaluable"}:
            raise AttestedQuerySnapshotError("root cell coverage item is invalid")
        normalized.append(parsed)
    if normalized != expected or _coverage_payload(normalized) != payload:
        raise AttestedQuerySnapshotError("coverage payload does not reproduce selected raw-leaf coverage")
    return tuple(_freeze(item) for item in normalized)


# ---------------------------------------------------------------------------
# B4B receipt-only reader
#
# The serving path deliberately validates only the v2 manifest plus its two
# compact public-receipt artifacts.  Calling the full snapshot loader here
# would re-read the v1 matrix/ledger/parquet and the B3/Company Facts bodies on
# every cold HTTP worker, turning a small receipt endpoint into a multi-GB
# request-time replay.  This reader therefore makes the narrower, explicit
# stored-receipt self-consistency claim only.
# ---------------------------------------------------------------------------


def _receipt_text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise AttestedQuerySnapshotError(f"{field} is invalid")
    try:
        too_long = len(value.encode("utf-8")) > 16 * 1024
    except UnicodeError as exc:
        raise AttestedQuerySnapshotError(f"{field} is invalid") from exc
    if too_long:
        raise AttestedQuerySnapshotError(f"{field} is invalid")
    return value


def _receipt_attestation_projections(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Validate the compact B3 projections retained in the v2 manifest.

    We intentionally do not read ``attestations_json`` here.  The projection is
    sufficient to bind an API-visible compact Company Facts correspondence to
    its stored B3 identifier, capture, filing identity, and match budget.
    """
    receipt = manifest["companyfacts_conversion_receipt"]
    if (
        not isinstance(receipt["capture_id"], str)
        or not _COMPANYFACTS_CAPTURE_ID_RE.fullmatch(receipt["capture_id"])
        or not isinstance(receipt["manifest_id"], str)
        or not _COMPANYFACTS_MANIFEST_ID_RE.fullmatch(receipt["manifest_id"])
        or not isinstance(receipt["cik"], str)
        or not _CIK_RE.fullmatch(receipt["cik"])
    ):
        raise AttestedQuerySnapshotError("Company Facts conversion receipt identity is invalid")
    verification = _utc(
        manifest["clocks"]["operator_verification_observed_at"],
        field="attested snapshot operator_verification_observed_at",
    )
    projections = manifest["attestation_projections"]
    if len(projections) > HARD_MAX_ATTESTED_RECEIPT_PROJECTIONS:
        raise AttestedQuerySnapshotError("attested receipt projection count exceeds serving budget")
    result: dict[str, dict[str, Any]] = {}
    previous: str | None = None
    for raw in projections:
        projection = _strict_object(
            raw,
            field="attested snapshot projection",
            required=frozenset({
                "attestation_id", "authority_snapshot_id", "package_id", "extraction_id", "cik", "accession",
                "companyfacts_capture_id", "companyfacts_manifest_id", "companyfacts_response_sha256",
                "companyfacts_match_count", "attested_at",
            }),
        )
        identifier = projection["attestation_id"]
        if (
            not isinstance(identifier, str)
            or not _ATTESTATION_ID_RE.fullmatch(identifier)
            or previous is not None and identifier <= previous
            or not isinstance(projection["authority_snapshot_id"], str)
            or not _SOURCE_SNAPSHOT_ID_RE.fullmatch(projection["authority_snapshot_id"])
            or not isinstance(projection["package_id"], str)
            or not _PACKAGE_ID_RE.fullmatch(projection["package_id"])
            or not isinstance(projection["extraction_id"], str)
            or not _EXTRACTION_ID_RE.fullmatch(projection["extraction_id"])
            or not isinstance(projection["cik"], str)
            or not _CIK_RE.fullmatch(projection["cik"])
            or not isinstance(projection["accession"], str)
            or not _ACCESSION_RE.fullmatch(projection["accession"])
            or not isinstance(projection["companyfacts_capture_id"], str)
            or not _COMPANYFACTS_CAPTURE_ID_RE.fullmatch(projection["companyfacts_capture_id"])
            or not isinstance(projection["companyfacts_manifest_id"], str)
            or not _COMPANYFACTS_MANIFEST_ID_RE.fullmatch(projection["companyfacts_manifest_id"])
            or not isinstance(projection["companyfacts_response_sha256"], str)
            or not _SHA_RE.fullmatch(projection["companyfacts_response_sha256"])
            or isinstance(projection["companyfacts_match_count"], bool)
            or not isinstance(projection["companyfacts_match_count"], int)
            or projection["companyfacts_match_count"] <= 0
        ):
            raise AttestedQuerySnapshotError("attested snapshot receipt projection is invalid")
        attested_at = _utc(projection["attested_at"], field="attested snapshot projection attested_at")
        if utc_text(attested_at) != projection["attested_at"] or attested_at > verification:
            raise AttestedQuerySnapshotError("attested snapshot receipt projection clock is invalid")
        if (
            projection["companyfacts_capture_id"] != receipt["capture_id"]
            or projection["companyfacts_manifest_id"] != receipt["manifest_id"]
            or projection["cik"] != receipt["cik"]
        ):
            raise AttestedQuerySnapshotError("attested snapshot receipt projection does not bind Company Facts receipt")
        result[identifier] = projection
        previous = identifier
    if not result:
        raise AttestedQuerySnapshotError("attested snapshot receipt has no projections")
    return result


def _receipt_binding_from_payload(
    item: Mapping[str, Any],
    *,
    projections: Mapping[str, Mapping[str, Any]],
    conversion_receipt: Mapping[str, Any],
) -> tuple[AttestedOccurrenceBinding, dict[str, Any]]:
    raw = _strict_object(
        item,
        field="attested receipt occurrence binding",
        required=frozenset({"occurrence_id", "attestation_id", "match_id", "companyfacts"}),
    )
    binding = AttestedOccurrenceBinding(raw["occurrence_id"], raw["attestation_id"], raw["match_id"])
    if not _RAW_OCCURRENCE_ID_RE.fullmatch(binding.occurrence_id):
        raise AttestedQuerySnapshotError("attested receipt occurrence id is invalid")
    projection = projections.get(binding.attestation_id)
    if projection is None:
        raise AttestedQuerySnapshotError("attested receipt binding references an unprojected attestation")
    companyfacts = _strict_object(
        raw["companyfacts"],
        field="attested receipt Company Facts projection",
        required=frozenset({
            "capture_id", "manifest_id", "response_sha256", "cik", "accession", "taxonomy", "concept", "unit",
            "entry_index", "start", "end", "value", "dimensions_known",
        }),
    )
    if (
        not isinstance(companyfacts["capture_id"], str)
        or not _COMPANYFACTS_CAPTURE_ID_RE.fullmatch(companyfacts["capture_id"])
        or not isinstance(companyfacts["manifest_id"], str)
        or not _COMPANYFACTS_MANIFEST_ID_RE.fullmatch(companyfacts["manifest_id"])
        or not isinstance(companyfacts["response_sha256"], str)
        or not _SHA_RE.fullmatch(companyfacts["response_sha256"])
        or not isinstance(companyfacts["cik"], str)
        or not _CIK_RE.fullmatch(companyfacts["cik"])
        or not isinstance(companyfacts["accession"], str)
        or not _ACCESSION_RE.fullmatch(companyfacts["accession"])
        or companyfacts["dimensions_known"] is not False
        or isinstance(companyfacts["entry_index"], bool)
        or not isinstance(companyfacts["entry_index"], int)
        or companyfacts["entry_index"] < 0
    ):
        raise AttestedQuerySnapshotError("attested receipt Company Facts projection is invalid")
    for field in ("taxonomy", "concept", "unit"):
        _receipt_text(companyfacts[field], field=f"attested receipt Company Facts {field}")
    _date_text(companyfacts["start"], field="attested receipt Company Facts start", nullable=True)
    _date_text(companyfacts["end"], field="attested receipt Company Facts end")
    if not isinstance(companyfacts["value"], str) or decimal_text(companyfacts["value"]) != companyfacts["value"]:
        raise AttestedQuerySnapshotError("attested receipt Company Facts value is invalid")
    if (
        companyfacts["capture_id"] != projection["companyfacts_capture_id"]
        or companyfacts["manifest_id"] != projection["companyfacts_manifest_id"]
        or companyfacts["response_sha256"] != projection["companyfacts_response_sha256"]
        or companyfacts["cik"] != projection["cik"]
        or companyfacts["accession"] != projection["accession"]
        or companyfacts["capture_id"] != conversion_receipt["capture_id"]
        or companyfacts["manifest_id"] != conversion_receipt["manifest_id"]
        or companyfacts["cik"] != conversion_receipt["cik"]
    ):
        raise AttestedQuerySnapshotError("attested receipt binding does not bind manifest Company Facts identity")
    return binding, {**binding.to_dict(), "companyfacts": companyfacts}


def _receipt_bindings(
    payload: bytes,
    *,
    projections: Mapping[str, Mapping[str, Any]],
    conversion_receipt: Mapping[str, Any],
) -> Mapping[str, Mapping[str, Any]]:
    raw = _json_object(payload, field="attested receipt bindings payload", limit=HARD_MAX_ATTESTED_SNAPSHOT_BINDINGS_BYTES)
    value = _strict_object(raw, field="attested receipt bindings payload", required=frozenset({"schema", "items"}))
    if (
        value["schema"] != _BINDINGS_PAYLOAD_SCHEMA
        or not isinstance(value["items"], list)
        or not value["items"]
        or len(value["items"]) > HARD_MAX_ATTESTED_RECEIPT_BINDINGS
    ):
        raise AttestedQuerySnapshotError("attested receipt bindings payload is invalid")
    normalized: list[dict[str, Any]] = []
    by_occurrence: dict[str, Mapping[str, Any]] = {}
    used_matches: set[tuple[str, str]] = set()
    counts_by_attestation: dict[str, int] = {}
    previous: str | None = None
    for item in value["items"]:
        if not isinstance(item, Mapping):
            raise AttestedQuerySnapshotError("attested receipt binding item is invalid")
        binding, parsed = _receipt_binding_from_payload(
            item,
            projections=projections,
            conversion_receipt=conversion_receipt,
        )
        if (
            binding.occurrence_id in by_occurrence
            or (binding.attestation_id, binding.match_id) in used_matches
            or previous is not None and binding.occurrence_id <= previous
        ):
            raise AttestedQuerySnapshotError("attested receipt bindings are not uniquely canonical")
        normalized.append(parsed)
        frozen = _freeze(parsed)
        assert isinstance(frozen, Mapping)
        by_occurrence[binding.occurrence_id] = frozen
        used_matches.add((binding.attestation_id, binding.match_id))
        counts_by_attestation[binding.attestation_id] = counts_by_attestation.get(binding.attestation_id, 0) + 1
        previous = binding.occurrence_id
    if set(counts_by_attestation) != set(projections) or any(
        count > projections[attestation_id]["companyfacts_match_count"]
        for attestation_id, count in counts_by_attestation.items()
    ):
        raise AttestedQuerySnapshotError("attested receipt bindings do not exhaust manifest attestation projections")
    if _binding_payload(normalized) != payload:
        raise AttestedQuerySnapshotError("attested receipt bindings payload is not canonical")
    return MappingProxyType(by_occurrence)


def _receipt_occurrence_ids(value: Any, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise AttestedQuerySnapshotError(f"{field} is invalid")
    result: list[str] = []
    previous: str | None = None
    for occurrence_id in value:
        if (
            not isinstance(occurrence_id, str)
            or not _RAW_OCCURRENCE_ID_RE.fullmatch(occurrence_id)
            or previous is not None and occurrence_id <= previous
        ):
            raise AttestedQuerySnapshotError(f"{field} is not canonical")
        result.append(occurrence_id)
        previous = occurrence_id
    return tuple(result)


def _receipt_coverage_status(
    *,
    selected: tuple[str, ...],
    eligible: tuple[str, ...],
    attested: tuple[str, ...],
) -> str:
    if not selected or not eligible:
        return "not_evaluable"
    if len(attested) == len(selected) and len(eligible) == len(selected):
        return "all_leaves_attested"
    if attested:
        return "partially_attested"
    return "not_attested"


def _receipt_roots(
    payload: bytes,
    *,
    binding_occurrence_ids: frozenset[str],
    manifest_summary: Mapping[str, Any],
) -> tuple[tuple[Mapping[str, Any], ...], int]:
    raw = _json_object(payload, field="attested receipt coverage payload", limit=HARD_MAX_ATTESTED_SNAPSHOT_COVERAGE_BYTES)
    value = _strict_object(raw, field="attested receipt coverage payload", required=frozenset({"schema", "items"}))
    if (
        value["schema"] != _COVERAGE_PAYLOAD_SCHEMA
        or not isinstance(value["items"], list)
        or len(value["items"]) > HARD_MAX_ATTESTED_RECEIPT_ROOT_CELLS
    ):
        raise AttestedQuerySnapshotError("attested receipt coverage payload is invalid")
    normalized: list[dict[str, Any]] = []
    seen_attested: set[str] = set()
    previous: str | None = None
    leaf_references = 0
    for item in value["items"]:
        parsed = _strict_object(
            item,
            field="attested receipt root coverage",
            required=frozenset({"root_cell_id", "selected_leaf_occurrence_ids", "eligible_leaf_occurrence_ids", "attested_occurrence_ids", "status"}),
        )
        root_cell_id = parsed["root_cell_id"]
        if (
            not isinstance(root_cell_id, str)
            or not _ROOT_CELL_ID_RE.fullmatch(root_cell_id)
            or previous is not None and root_cell_id <= previous
        ):
            raise AttestedQuerySnapshotError("attested receipt root coverage is not uniquely canonical")
        selected = _receipt_occurrence_ids(parsed["selected_leaf_occurrence_ids"], field="attested receipt selected leaves")
        eligible = _receipt_occurrence_ids(parsed["eligible_leaf_occurrence_ids"], field="attested receipt eligible leaves")
        attested = _receipt_occurrence_ids(parsed["attested_occurrence_ids"], field="attested receipt attested leaves")
        leaf_references += len(selected) + len(eligible) + len(attested)
        if leaf_references > HARD_MAX_ATTESTED_RECEIPT_LEAF_REFERENCES:
            raise AttestedQuerySnapshotError("attested receipt leaf-reference count exceeds serving budget")
        selected_set = frozenset(selected)
        if not frozenset(eligible).issubset(selected_set) or not frozenset(attested).issubset(frozenset(eligible)):
            raise AttestedQuerySnapshotError("attested receipt root coverage subset relation is invalid")
        if parsed["status"] != _receipt_coverage_status(selected=selected, eligible=eligible, attested=attested):
            raise AttestedQuerySnapshotError("attested receipt root coverage status is invalid")
        normalized.append(parsed)
        seen_attested.update(attested)
        previous = root_cell_id
    if seen_attested != binding_occurrence_ids:
        raise AttestedQuerySnapshotError("attested receipt bindings and root coverage disagree")
    if _coverage_summary(normalized) != _thaw(manifest_summary):
        raise AttestedQuerySnapshotError("attested receipt coverage summary does not bind roots")
    if _coverage_payload(normalized) != payload:
        raise AttestedQuerySnapshotError("attested receipt coverage payload is not canonical")
    return tuple(_freeze(item) for item in normalized), leaf_references


def _receipt_artifact_payload(
    store: StrictBoundedReadStore,
    artifact: AttestedQuerySnapshotArtifact,
) -> bytes:
    payload = _read_exact_bounded(
        store,
        artifact.object_key,
        expected_byte_length=artifact.byte_length,
        maximum=_ROLE_LIMITS[artifact.role],
    )
    if sha256(payload).hexdigest() != artifact.sha256:
        raise AttestedQuerySnapshotError("attested receipt object digest mismatch")
    return payload


def _receipt_manifest_from_store(
    store: StrictBoundedReadStore,
    *,
    snapshot_id: str,
) -> tuple[dict[str, Any], int]:
    """Read and canonical-validate one immutable manifest before cache use."""
    snapshot_id = _snapshot_id(snapshot_id)
    manifest_key = _manifest_key(snapshot_id)
    payload = _read_bounded(store, manifest_key, maximum=HARD_MAX_ATTESTED_SNAPSHOT_MANIFEST_BYTES)
    manifest = _decode_manifest(payload)
    if manifest["snapshot_id"] != snapshot_id:
        raise AttestedQuerySnapshotError("attested receipt manifest does not bind requested snapshot")
    return manifest, len(payload)


def _receipt_artifacts_from_manifest(manifest: Mapping[str, Any]) -> Mapping[str, AttestedQuerySnapshotArtifact]:
    artifacts = tuple(AttestedQuerySnapshotArtifact(**item) for item in manifest["objects"])
    artifacts_by_role = {artifact.role: artifact for artifact in artifacts}
    if tuple(artifacts_by_role) != _ROLES or len(artifacts_by_role) != len(_ROLES):
        raise AttestedQuerySnapshotError("attested receipt manifest objects are invalid")
    return MappingProxyType(artifacts_by_role)


def _receipt_compact_artifact_budget(
    artifacts_by_role: Mapping[str, AttestedQuerySnapshotArtifact],
) -> int:
    """Refuse an oversized HTTP receipt before reading either compact object."""
    compact_bytes = sum(
        artifacts_by_role[role].byte_length
        for role in ("bindings_json", "coverage_json")
    )
    if compact_bytes > HARD_MAX_ATTESTED_RECEIPT_COMPACT_BYTES:
        raise AttestedQuerySnapshotError("attested receipt compact artifacts exceed serving byte budget")
    return compact_bytes


def _receipt_index_weight(
    *,
    manifest_bytes: int,
    compact_bytes: int,
    projection_count: int,
    binding_count: int,
    root_count: int,
    leaf_references: int,
) -> int:
    """Conservative retained-memory estimate for a frozen receipt index.

    JSON byte size alone is not a cache budget: decoding plus frozen maps,
    identifier indexes, and repeated occurrence references consume materially
    more heap.  The fixed conservative multipliers make cache admission stable
    across Python allocator details while the cardinality checks above cap every
    component before it can grow without bound.
    """
    values = (manifest_bytes, compact_bytes, projection_count, binding_count, root_count, leaf_references)
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
        raise AttestedQuerySnapshotError("attested receipt decoded index budget is invalid")
    weight = (
        2 * manifest_bytes
        + 3 * compact_bytes
        + 768 * projection_count
        + 896 * binding_count
        + 448 * root_count
        + 144 * leaf_references
    )
    if weight > HARD_MAX_ATTESTED_RECEIPT_DECODED_INDEX_BYTES:
        raise AttestedQuerySnapshotError("attested receipt decoded index exceeds serving budget")
    return weight


def _receipt_index_from_manifest(
    store: StrictBoundedReadStore,
    *,
    snapshot_id: str,
    manifest: Mapping[str, Any],
    manifest_byte_length: int,
) -> tuple[AttestedQueryReceiptIndex, int]:
    """Build one cacheable index while reading only compact receipt objects."""
    artifacts_by_role = _receipt_artifacts_from_manifest(manifest)
    compact_bytes = _receipt_compact_artifact_budget(artifacts_by_role)
    # Do not add a convenience read of either omitted payload.  The HTTP
    # reader's bounded shape is part of the privacy and latency contract.
    bindings_payload = _receipt_artifact_payload(store, artifacts_by_role["bindings_json"])
    coverage_payload = _receipt_artifact_payload(store, artifacts_by_role["coverage_json"])
    projections = _receipt_attestation_projections(manifest)
    bindings = _receipt_bindings(
        bindings_payload,
        projections=projections,
        conversion_receipt=manifest["companyfacts_conversion_receipt"],
    )
    roots, leaf_references = _receipt_roots(
        coverage_payload,
        binding_occurrence_ids=frozenset(bindings),
        manifest_summary=manifest["coverage_summary"],
    )
    root_ids = tuple(root["root_cell_id"] for root in roots)
    roots_by_id = MappingProxyType({root_id: root for root_id, root in zip(root_ids, roots)})
    if len(roots_by_id) != len(root_ids):
        raise AttestedQuerySnapshotError("attested receipt root index is not unique")
    frozen_manifest = _freeze(manifest)
    assert isinstance(frozen_manifest, Mapping)
    frozen_projections = {
        identifier: frozen_manifest["attestation_projections"][index]
        for index, identifier in enumerate(sorted(projections))
    }
    if any(not isinstance(value, Mapping) for value in frozen_projections.values()):
        raise AttestedQuerySnapshotError("attested receipt projection freeze failed")
    index = AttestedQueryReceiptIndex(
        snapshot_id=snapshot_id,
        manifest_key=_manifest_key(snapshot_id),
        base_snapshot_id=manifest["base_snapshot"]["snapshot_id"],
        query_hash=manifest["base_snapshot"]["query_hash"],
        manifest=frozen_manifest,
        roots=roots,
        root_ids=root_ids,
        roots_by_id=roots_by_id,
        bindings_by_occurrence=bindings,
        attestations_by_id=MappingProxyType(frozen_projections),
        published_at=_utc(manifest["clocks"]["published_at"], field="attested receipt published_at"),
    )
    return index, _receipt_index_weight(
        manifest_bytes=manifest_byte_length,
        compact_bytes=compact_bytes,
        projection_count=len(projections),
        binding_count=len(bindings),
        root_count=len(roots),
        leaf_references=leaf_references,
    )


def _receipt_index_cache_get(store: StrictBoundedReadStore, *, snapshot_id: str) -> AttestedQueryReceiptIndex | None:
    global _RECEIPT_INDEX_CACHE_BYTES
    key = (id(store), snapshot_id)
    with _RECEIPT_INDEX_CACHE_LOCK:
        cached = _RECEIPT_INDEX_CACHE.get(key)
        if cached is None:
            return None
        cached_store, index, _byte_cost = cached
        if cached_store is not store:
            # An object id can be reused after a short-lived proxy is gone.
            # Never let that turn a different private store into a cache hit.
            _RECEIPT_INDEX_CACHE_BYTES -= _RECEIPT_INDEX_CACHE.pop(key)[2]
            return None
        _RECEIPT_INDEX_CACHE.move_to_end(key)
        return index


def _receipt_index_cache_put(
    store: StrictBoundedReadStore,
    index: AttestedQueryReceiptIndex,
    *,
    byte_cost: int,
) -> AttestedQueryReceiptIndex:
    global _RECEIPT_INDEX_CACHE_BYTES
    if byte_cost > _RECEIPT_INDEX_CACHE_MAX_BYTES:
        return index
    key = (id(store), index.snapshot_id)
    with _RECEIPT_INDEX_CACHE_LOCK:
        prior = _RECEIPT_INDEX_CACHE.pop(key, None)
        if prior is not None:
            _RECEIPT_INDEX_CACHE_BYTES -= prior[2]
        _RECEIPT_INDEX_CACHE[key] = (store, index, byte_cost)
        _RECEIPT_INDEX_CACHE_BYTES += byte_cost
        _RECEIPT_INDEX_CACHE.move_to_end(key)
        while (
            len(_RECEIPT_INDEX_CACHE) > _RECEIPT_INDEX_CACHE_MAX_ENTRIES
            or _RECEIPT_INDEX_CACHE_BYTES > _RECEIPT_INDEX_CACHE_MAX_BYTES
        ):
            _evicted_key, (_evicted_store, _evicted_index, evicted_bytes) = _RECEIPT_INDEX_CACHE.popitem(last=False)
            del _evicted_key, _evicted_store, _evicted_index
            _RECEIPT_INDEX_CACHE_BYTES -= evicted_bytes
    return index


def _receipt_index_cache_discard(store: StrictBoundedReadStore, *, snapshot_id: str) -> None:
    """Forget a stale/corrupt projection before another caller can reuse it."""
    global _RECEIPT_INDEX_CACHE_BYTES
    key = (id(store), snapshot_id)
    with _RECEIPT_INDEX_CACHE_LOCK:
        cached = _RECEIPT_INDEX_CACHE.get(key)
        if cached is None or cached[0] is not store:
            return
        _RECEIPT_INDEX_CACHE_BYTES -= _RECEIPT_INDEX_CACHE.pop(key)[2]


def _receipt_singleflight_stripe(
    store: StrictBoundedReadStore,
    *,
    snapshot_id: str,
) -> _ReceiptIndexFlightStripe:
    """Choose one fixed flight slot without retaining attacker-selected keys."""
    return _RECEIPT_INDEX_SINGLEFLIGHT_STRIPES[
        hash((id(store), snapshot_id)) % len(_RECEIPT_INDEX_SINGLEFLIGHT_STRIPES)
    ]


def _assert_receipt_pointer(
    index: AttestedQueryReceiptIndex,
    pointer: AttestedQuerySnapshotPointer | None,
) -> None:
    if pointer is not None and (
        index.manifest_key != pointer.manifest_key
        or index.base_snapshot_id != pointer.base_snapshot_id
        or index.published_at != pointer.published_at
    ):
        raise AttestedQuerySnapshotError("attested receipt latest pointer does not bind manifest")


def _load_receipt_index_serial(
    store: StrictBoundedReadStore,
    *,
    snapshot_id: str,
    pointer: AttestedQuerySnapshotPointer | None,
) -> AttestedQueryReceiptIndex:
    """Do one fully revalidated read while its per-key singleflight is held."""
    manifest, manifest_byte_length = _receipt_manifest_from_store(store, snapshot_id=snapshot_id)
    index = _receipt_index_cache_get(store, snapshot_id=snapshot_id)
    if index is None:
        index, cache_weight = _receipt_index_from_manifest(
            store,
            snapshot_id=snapshot_id,
            manifest=manifest,
            manifest_byte_length=manifest_byte_length,
        )
        index = _receipt_index_cache_put(store, index, byte_cost=cache_weight)
    elif _thaw(index.manifest) != manifest:
        # This should be cryptographically impossible for a valid snapshot id,
        # but never allow a mutable backend to turn a prior cache hit into a
        # silent latest response.
        _receipt_index_cache_discard(store, snapshot_id=snapshot_id)
        raise AttestedQuerySnapshotError("attested receipt cached manifest disagrees with storage")
    else:
        # A cache stores only parsed data.  Re-read and digest-check the two
        # compact immutable artifacts for ordinary cache hits; a concurrent
        # cold waiter below can safely share its leader's just-completed check.
        artifacts_by_role = _receipt_artifacts_from_manifest(manifest)
        _receipt_compact_artifact_budget(artifacts_by_role)
        _receipt_artifact_payload(store, artifacts_by_role["bindings_json"])
        _receipt_artifact_payload(store, artifacts_by_role["coverage_json"])
    _assert_receipt_pointer(index, pointer)
    return index


def reset_attested_query_receipt_index_cache() -> None:
    """Clear the bounded receipt-reader cache (a deterministic test seam)."""
    global _RECEIPT_INDEX_CACHE_BYTES
    with _RECEIPT_INDEX_CACHE_LOCK:
        _RECEIPT_INDEX_CACHE.clear()
        _RECEIPT_INDEX_CACHE_BYTES = 0


def load_attested_query_receipt_index(
    store: StrictBoundedReadStore,
    *,
    snapshot_id: str | None = None,
) -> AttestedQueryReceiptIndex:
    """Load a compact, immutable B4 history receipt without source renewal.

    ``snapshot_id=None`` always re-reads the independent v2 pointer before a
    cache lookup.  Ordinary cache hits also re-read the canonical manifest and
    two compact artifacts.  A contending cold caller shares the preceding
    leader's just-completed fully checked immutable projection instead of
    duplicating the same R2 download and parse; failed reads discard cache
    state and are never shared.
    """
    store = _require_store(store)
    pointer: AttestedQuerySnapshotPointer | None = None
    if snapshot_id is None:
        pointer = _decode_pointer(_read_bounded(store, _latest_key(), maximum=16 * 1024))
        requested = pointer.snapshot_id
    else:
        requested = _snapshot_id(snapshot_id)
    stripe = _receipt_singleflight_stripe(store, snapshot_id=requested)
    while True:
        with stripe.lock:
            flight = stripe.flight
            if flight is None:
                flight = _ReceiptIndexFlight(
                    store=store,
                    snapshot_id=requested,
                    done=Event(),
                )
                stripe.flight = flight
                leader = True
                collision = None
            elif flight.store is store and flight.snapshot_id == requested:
                leader = False
                collision = None
            else:
                # A different key landed on this fixed stripe.  Queue behind
                # it without allocating an unbounded per-key flight registry.
                leader = False
                collision = flight

        if collision is not None:
            collision.done.wait()
            continue

        if not leader:
            # This caller joined the same active load generation, so it shares
            # the leader's fully validated in-memory result rather than doing
            # another warm-cache artifact download.  It still checks its own
            # independently read latest pointer before returning.
            flight.done.wait()
            if flight.error is not None:
                raise flight.error
            if flight.index is None:  # pragma: no cover - protects future edits.
                raise AttestedQuerySnapshotError("attested receipt singleflight completed without a result")
            _assert_receipt_pointer(flight.index, pointer)
            return flight.index

        try:
            index = _load_receipt_index_serial(store, snapshot_id=requested, pointer=pointer)
        except BaseException as exc:
            _receipt_index_cache_discard(store, snapshot_id=requested)
            flight.error = exc
            raise
        else:
            flight.index = index
            return index
        finally:
            # Wake same-generation callers before removing the bounded flight
            # slot.  Late callers start a normal cache-validated read instead.
            flight.done.set()
            with stripe.lock:
                if stripe.flight is flight:
                    stripe.flight = None


def _required_verification_clock(base: QuerySnapshot, records: Mapping[str, Mapping[str, Any]], conversion: CompanyFactsLedgerConversion) -> datetime:
    values = [
        _utc(base.manifest["clocks"][name], field=f"base.{name}")
        for name in ("source_snapshot_at", "recorded_at", "computed_at", "published_at")
    ]
    for record in records.values():
        values.extend(
            _utc(record["clocks"][name], field=f"attestation.{name}")
            for name in ("source_snapshot_at", "filing_manifest_recorded_at", "package_assembled_at", "extraction_computed_at", "attested_at")
        )
        cf = record["company_facts"]
        values.extend(_utc(cf[name], field=f"attestation.company_facts.{name}") for name in ("captured_at", "recorded_at"))
    values.extend(_utc(value, field=f"conversion.{name}") for name, value in conversion.receipt.clocks)
    return max(values)


def prepare_attested_query_snapshot(
    *,
    store: StrictBoundedReadStore,
    query_snapshot_id: str | None = None,
    base_snapshot_id: str | None = None,
    attestation_materials: Sequence[AttestationMaterial],
    companyfacts_conversion: CompanyFactsLedgerConversion,
    occurrence_bindings: Sequence[AttestedOccurrenceBinding],
    operator_verification_observed_at: datetime | str,
    published_at: datetime | str,
) -> PreparedAttestedQuerySnapshot:
    """Prepare a v2 overlay on one explicit, already-published v1 receipt.

    ``occurrence_bindings`` intentionally names the selection rather than
    guessing it from an accession.  Missing bindings remain visible as partial
    root-cell coverage; an overlay with no valid selection correspondence is
    rejected because it would add only a more persuasive-looking wrapper.
    """
    store = _require_store(store)
    if (query_snapshot_id is None) == (base_snapshot_id is None):
        raise AttestedQuerySnapshotError("supply exactly one of query_snapshot_id or base_snapshot_id")
    requested = _v1_snapshot_id(query_snapshot_id if query_snapshot_id is not None else base_snapshot_id or "")
    base = _verified_base_snapshot(store, requested)
    if type(companyfacts_conversion) is not CompanyFactsLedgerConversion:
        raise AttestedQuerySnapshotError("companyfacts_conversion must be an exact CompanyFactsLedgerConversion")
    try:
        companyfacts_conversion.__post_init__()
    except (TypeError, ValueError) as exc:
        raise AttestedQuerySnapshotError(f"Company Facts conversion invariant failed: {exc}") from exc
    verification = _utc(
        operator_verification_observed_at,
        field="operator_verification_observed_at",
    )
    publication = _utc(published_at, field="published_at")
    records = _material_map(attestation_materials)
    if verification < _required_verification_clock(base, records, companyfacts_conversion):
        raise AttestedQuerySnapshotError("operator verification observed clock predates the query, B3, or Company Facts evidence")
    if publication < verification:
        raise AttestedQuerySnapshotError("attested snapshot published_at predates operator verification observed clock")
    binding_records, roots = _validated_bindings(
        base=base,
        conversion=companyfacts_conversion,
        records=records,
        bindings=occurrence_bindings,
    )
    # Require exact selected leaf occurrence membership after the conversion
    # join.  This preserves the meaning of a shared selected raw leaf while
    # permitting other cells to remain visibly un-attested.
    if not binding_records:
        raise AttestedQuerySnapshotError("attested query snapshot requires at least one valid occurrence binding")
    coverage_rows = _coverage_rows(roots, binding_records, _eligible_leaf_ids(base))
    attestations_payload = _attestations_payload(records)
    conversion_payload = _conversion_payload(companyfacts_conversion)
    bindings_payload = _binding_payload(binding_records)
    coverage_payload = _coverage_payload(coverage_rows)
    artifacts = (
        _artifact("attestations_json", attestations_payload),
        _artifact("companyfacts_conversion_json", conversion_payload),
        _artifact("bindings_json", bindings_payload),
        _artifact("coverage_json", coverage_payload),
    )
    body = _manifest_body(
        base=base,
        records=records,
        coverage_rows=coverage_rows,
        conversion=companyfacts_conversion,
        artifacts=artifacts,
        operator_verification_observed_at=utc_text(verification) or "",
        published_at=utc_text(publication) or "",
    )
    snapshot_id = _identity(body)
    manifest = {"snapshot_id": snapshot_id, **body}
    manifest_bytes = _manifest_bytes(manifest)
    if _decode_manifest(manifest_bytes) != manifest:
        raise AttestedQuerySnapshotError("attested snapshot manifest local verification failed")
    return PreparedAttestedQuerySnapshot(
        snapshot_id=snapshot_id,
        manifest_key=_manifest_key(snapshot_id),
        manifest=_freeze(manifest),
        artifacts=artifacts,
        payloads=MappingProxyType({"attestations_json": attestations_payload, "companyfacts_conversion_json": conversion_payload, "bindings_json": bindings_payload, "coverage_json": coverage_payload}),
    )


def _read_optional(store: StrictBoundedReadStore, key: str, *, maximum: int) -> bytes | None:
    return _read_bounded(store, key, maximum=maximum, required=False)


def _put_immutable(store: StrictBoundedReadStore, artifact: AttestedQuerySnapshotArtifact, payload: bytes) -> None:
    existing = _read_optional(store, artifact.object_key, maximum=_ROLE_LIMITS[artifact.role])
    if existing is None:
        try:
            written = store.put_bytes(artifact.object_key, payload, content_type=artifact.content_type)
        except Exception as exc:  # noqa: BLE001
            raise AttestedQuerySnapshotError(f"private attested snapshot write failed for {artifact.object_key}") from exc
        if written is not True:
            raise AttestedQuerySnapshotError("private attested snapshot immutable write failed")
    elif existing != payload:
        raise AttestedQuerySnapshotError("attested snapshot immutable object collision")
    echoed = _read_bounded(store, artifact.object_key, maximum=_ROLE_LIMITS[artifact.role])
    if echoed != payload or sha256(echoed).hexdigest() != artifact.sha256:
        raise AttestedQuerySnapshotError("attested snapshot immutable object read-back mismatch")


def _pointer_from_dict(value: Mapping[str, Any]) -> AttestedQuerySnapshotPointer:
    raw = _strict_object(value, field="attested snapshot pointer", required=frozenset({"schema", "snapshot_id", "manifest_key", "base_snapshot_id", "published_at"}))
    return AttestedQuerySnapshotPointer(**raw)


def _decode_pointer(payload: bytes) -> AttestedQuerySnapshotPointer:
    raw = _json_object(payload, field="attested snapshot pointer", limit=16 * 1024)
    try:
        pointer = _pointer_from_dict(raw)
    except (TypeError, ValueError, AttestedQuerySnapshotError) as exc:
        raise AttestedQuerySnapshotError(f"attested snapshot pointer is invalid: {exc}") from exc
    if pointer.to_json_bytes() != payload:
        raise AttestedQuerySnapshotError("attested snapshot pointer is not canonical")
    return pointer


def _publish_pointer(store: StrictBoundedReadStore, snapshot: AttestedQuerySnapshot) -> None:
    pointer = AttestedQuerySnapshotPointer(
        snapshot_id=snapshot.snapshot_id,
        manifest_key=snapshot.manifest_key,
        base_snapshot_id=snapshot.base_snapshot_id,
        published_at=snapshot.published_at,
    )
    payload = pointer.to_json_bytes()
    prior = _read_optional(store, _latest_key(), maximum=16 * 1024)
    if prior is not None:
        old = _decode_pointer(prior)
        if old.snapshot_id == pointer.snapshot_id:
            if prior != payload:
                raise AttestedQuerySnapshotError("attested snapshot latest pointer disagrees with immutable snapshot")
            return
        if pointer.published_at <= old.published_at:
            raise AttestedQuerySnapshotError("stale attested snapshot cannot rewind independent latest pointer")
    try:
        written = store.put_bytes(_latest_key(), payload, content_type="application/json")
    except Exception as exc:  # noqa: BLE001
        raise AttestedQuerySnapshotError("attested snapshot latest pointer write failed") from exc
    if written is not True:
        raise AttestedQuerySnapshotError("attested snapshot latest pointer write failed")
    echoed = _read_optional(store, _latest_key(), maximum=16 * 1024)
    if echoed == payload:
        return
    if prior is not None:
        try:
            store.put_bytes(_latest_key(), prior, content_type="application/json")
        except Exception:
            pass
    raise AttestedQuerySnapshotError("attested snapshot latest pointer read-back mismatch")


def _validate_prepared(
    prepared: PreparedAttestedQuerySnapshot,
) -> tuple[
    dict[str, Any],
    tuple[AttestedQuerySnapshotArtifact, ...],
    Mapping[str, bytes],
    bytes,
]:
    """Freeze a caller-provided prepared value before semantic preflight.

    ``PreparedAttestedQuerySnapshot`` is intentionally public and therefore
    not a trust boundary.  Publication admits only exact finite containers,
    takes one local byte snapshot, and returns those captured values so no
    later write re-reads a caller-controlled mapping.
    """
    if type(prepared) is not PreparedAttestedQuerySnapshot:
        raise TypeError("prepared must be an exact PreparedAttestedQuerySnapshot")
    _snapshot_id(prepared.snapshot_id)
    if prepared.manifest_key != _manifest_key(prepared.snapshot_id):
        raise AttestedQuerySnapshotError("prepared attested snapshot manifest key is invalid")
    if type(prepared.manifest) not in (dict, _MAPPINGPROXY_TYPE):
        raise AttestedQuerySnapshotError("prepared attested snapshot manifest container is invalid")
    manifest_payload = _manifest_bytes(prepared.manifest)
    manifest = _decode_manifest(manifest_payload)
    if manifest["snapshot_id"] != prepared.snapshot_id:
        raise AttestedQuerySnapshotError("prepared attested snapshot id does not bind manifest")
    if (
        type(prepared.artifacts) is not tuple
        or any(type(item) is not AttestedQuerySnapshotArtifact for item in prepared.artifacts)
        or tuple(item.role for item in prepared.artifacts) != _ROLES
    ):
        raise AttestedQuerySnapshotError("prepared attested snapshot artifacts are not canonical")
    artifacts = tuple(prepared.artifacts)
    if manifest["objects"] != [item.to_dict() for item in artifacts]:
        raise AttestedQuerySnapshotError("prepared attested snapshot artifacts do not match manifest")
    if type(prepared.payloads) not in (dict, _MAPPINGPROXY_TYPE) or set(prepared.payloads) != set(_ROLES):
        raise AttestedQuerySnapshotError("prepared attested snapshot payload container is invalid")
    payloads: dict[str, bytes] = {}
    for artifact in artifacts:
        payload = prepared.payloads[artifact.role]
        if type(payload) is not bytes or len(payload) != artifact.byte_length or sha256(payload).hexdigest() != artifact.sha256:
            raise AttestedQuerySnapshotError("prepared attested snapshot payload does not bind artifact")
        payloads[artifact.role] = payload
    return manifest, artifacts, MappingProxyType(payloads), manifest_payload


def _validate_dependency_clocks(
    *,
    manifest: Mapping[str, Any],
    base: QuerySnapshot,
    records: Mapping[str, Mapping[str, Any]],
    conversion: CompanyFactsLedgerConversion,
) -> None:
    clocks = manifest["clocks"]
    expected_query = {
        "query_source_snapshot_at": base.manifest["clocks"]["source_snapshot_at"],
        "query_recorded_at": base.manifest["clocks"]["recorded_at"],
        "query_computed_at": base.manifest["clocks"]["computed_at"],
        "query_published_at": base.manifest["clocks"]["published_at"],
    }
    if any(clocks[name] != value for name, value in expected_query.items()):
        raise AttestedQuerySnapshotError("attested snapshot query clocks do not bind base snapshot")
    observed = _utc(
        clocks["operator_verification_observed_at"],
        field="operator_verification_observed_at",
    )
    if observed < _required_verification_clock(base, records, conversion):
        raise AttestedQuerySnapshotError(
            "operator verification observed clock predates the query, B3, or Company Facts evidence"
        )


def _preflight_prepared_publication(
    *,
    store: StrictBoundedReadStore,
    manifest: Mapping[str, Any],
    payloads: Mapping[str, bytes],
    attestation_materials: Sequence[AttestationMaterial],
    companyfacts_conversion: CompanyFactsLedgerConversion,
) -> None:
    """Renew every external claim and replay the full overlay before writes."""
    base = _verified_base_snapshot(store, manifest["base_snapshot"]["snapshot_id"])
    if _base_projection(base) != manifest["base_snapshot"]:
        raise AttestedQuerySnapshotError("prepared attested snapshot base receipt does not match manifest")

    records = _material_map(attestation_materials)
    if _attestations_payload(records) != payloads["attestations_json"]:
        raise AttestedQuerySnapshotError("prepared attestations do not exactly match renewed source materials")
    restored_records = _decode_attestations(
        payloads["attestations_json"], manifest["attestation_projections"]
    )

    if type(companyfacts_conversion) is not CompanyFactsLedgerConversion:
        raise AttestedQuerySnapshotError("companyfacts_conversion must be an exact CompanyFactsLedgerConversion")
    if _conversion_payload(companyfacts_conversion) != payloads["companyfacts_conversion_json"]:
        raise AttestedQuerySnapshotError("prepared Company Facts conversion does not exactly match external conversion")
    if companyfacts_conversion.receipt.to_dict() != manifest["companyfacts_conversion_receipt"]:
        raise AttestedQuerySnapshotError("prepared Company Facts conversion receipt does not match manifest")

    bindings, normalized_bindings = _decode_bindings(
        payloads["bindings_json"], restored_records
    )
    replayed_bindings, _ = _validated_bindings(
        base=base,
        conversion=companyfacts_conversion,
        records=restored_records,
        bindings=bindings,
    )
    if _binding_payload(replayed_bindings) != payloads["bindings_json"]:
        raise AttestedQuerySnapshotError("prepared occurrence bindings do not reproduce exact joins")
    coverage = _decode_coverage(
        payloads["coverage_json"],
        base=base,
        conversion=companyfacts_conversion,
        bindings=normalized_bindings,
    )
    if _coverage_summary(coverage) != manifest["coverage_summary"]:
        raise AttestedQuerySnapshotError("prepared coverage summary does not bind coverage rows")
    _validate_dependency_clocks(
        manifest=manifest,
        base=base,
        records=restored_records,
        conversion=companyfacts_conversion,
    )


def _snapshot_from_manifest(store: StrictBoundedReadStore, *, snapshot_id: str) -> AttestedQuerySnapshot:
    snapshot_id = _snapshot_id(snapshot_id)
    manifest_key = _manifest_key(snapshot_id)
    manifest = _decode_manifest(_read_bounded(store, manifest_key, maximum=HARD_MAX_ATTESTED_SNAPSHOT_MANIFEST_BYTES))
    if manifest["snapshot_id"] != snapshot_id:
        raise AttestedQuerySnapshotError("attested snapshot manifest does not match requested id")
    base_ref = manifest["base_snapshot"]
    base = _verified_base_snapshot(store, base_ref["snapshot_id"])
    if _base_projection(base) != base_ref:
        raise AttestedQuerySnapshotError("attested snapshot base receipt does not match manifest")
    artifacts = tuple(AttestedQuerySnapshotArtifact(**item) for item in manifest["objects"])
    payloads: dict[str, bytes] = {}
    for artifact in artifacts:
        payload = _read_bounded(store, artifact.object_key, maximum=_ROLE_LIMITS[artifact.role])
        if len(payload) != artifact.byte_length or sha256(payload).hexdigest() != artifact.sha256:
            raise AttestedQuerySnapshotError("attested snapshot object digest mismatch")
        payloads[artifact.role] = payload
    records = _decode_attestations(payloads["attestations_json"], manifest["attestation_projections"])
    conversion = _decode_conversion(payloads["companyfacts_conversion_json"], manifest["companyfacts_conversion_receipt"])
    _validate_dependency_clocks(
        manifest=manifest,
        base=base,
        records=records,
        conversion=conversion,
    )
    bindings, normalized_bindings = _decode_bindings(payloads["bindings_json"], records)
    replayed_bindings, roots = _validated_bindings(base=base, conversion=conversion, records=records, bindings=bindings)
    if _binding_payload(replayed_bindings) != payloads["bindings_json"]:
        raise AttestedQuerySnapshotError("stored occurrence bindings do not reproduce against stored Company Facts conversion")
    coverage = _decode_coverage(payloads["coverage_json"], base=base, conversion=conversion, bindings=normalized_bindings)
    if _coverage_summary(coverage) != manifest["coverage_summary"]:
        raise AttestedQuerySnapshotError("attested snapshot coverage summary does not bind coverage rows")
    if not bindings:
        raise AttestedQuerySnapshotError("attested snapshot must retain at least one occurrence binding")
    return AttestedQuerySnapshot(
        snapshot_id=snapshot_id,
        manifest_key=manifest_key,
        manifest=_freeze(manifest),
        base_snapshot=base,
        companyfacts_conversion=conversion,
        attestations=records,
        bindings=bindings,
        cell_coverage=coverage,
    )


def publish_attested_query_snapshot(
    store: StrictBoundedReadStore,
    prepared: PreparedAttestedQuerySnapshot,
    *,
    attestation_materials: Sequence[AttestationMaterial],
    companyfacts_conversion: CompanyFactsLedgerConversion,
) -> AttestedQuerySnapshot:
    """Renew, replay, write immutable objects, then advance only v2 latest.

    A caller-constructed ``PreparedAttestedQuerySnapshot`` is never authority.
    Publication requires the exact external materials again and completes the
    same source, conversion, join, coverage, and causal-clock checks before it
    writes even an orphaned content-addressed object.
    """
    store = _require_store(store)
    manifest, artifacts, payloads, manifest_payload = _validate_prepared(prepared)
    snapshot_id = manifest["snapshot_id"]
    manifest_key = _manifest_key(snapshot_id)
    _preflight_prepared_publication(
        store=store,
        manifest=manifest,
        payloads=payloads,
        attestation_materials=attestation_materials,
        companyfacts_conversion=companyfacts_conversion,
    )
    with _PUBLISH_LOCK:
        for artifact in artifacts:
            _put_immutable(store, artifact, payloads[artifact.role])
        existing = _read_optional(store, manifest_key, maximum=HARD_MAX_ATTESTED_SNAPSHOT_MANIFEST_BYTES)
        if existing is None:
            try:
                written = store.put_bytes(manifest_key, manifest_payload, content_type="application/json")
            except Exception as exc:  # noqa: BLE001
                raise AttestedQuerySnapshotError("attested snapshot manifest write failed") from exc
            if written is not True:
                raise AttestedQuerySnapshotError("attested snapshot manifest write failed")
        elif existing != manifest_payload:
            raise AttestedQuerySnapshotError("attested snapshot immutable manifest collision")
        if _read_bounded(store, manifest_key, maximum=HARD_MAX_ATTESTED_SNAPSHOT_MANIFEST_BYTES) != manifest_payload:
            raise AttestedQuerySnapshotError("attested snapshot manifest read-back mismatch")
        snapshot = _snapshot_from_manifest(store, snapshot_id=snapshot_id)
        _publish_pointer(store, snapshot)
        return snapshot


def load_attested_query_snapshot(store: StrictBoundedReadStore, *, snapshot_id: str | None = None) -> AttestedQuerySnapshot:
    """Load an immutable v2 overlay by ID or its independent latest pointer."""
    store = _require_store(store)
    if snapshot_id is None:
        pointer = _decode_pointer(_read_bounded(store, _latest_key(), maximum=16 * 1024))
        snapshot = _snapshot_from_manifest(store, snapshot_id=pointer.snapshot_id)
        if snapshot.manifest_key != pointer.manifest_key or snapshot.base_snapshot_id != pointer.base_snapshot_id or snapshot.published_at != pointer.published_at:
            raise AttestedQuerySnapshotError("attested snapshot latest pointer does not bind manifest")
        return snapshot
    return _snapshot_from_manifest(store, snapshot_id=_snapshot_id(snapshot_id))


def verify_attested_query_snapshot(store: StrictBoundedReadStore, *, snapshot_id: str | None = None) -> AttestedQuerySnapshot:
    """Verify v2 canonical storage plus the renewable v1 query replay.

    This self-consistency check does not renew B3 source evidence.  Call
    :func:`verify_attested_query_snapshot_source` with the exact external
    package/extraction/authority/conversion materials before relying on a
    filing-backed correspondence claim.
    """
    return load_attested_query_snapshot(store, snapshot_id=snapshot_id)


def verify_attested_query_snapshot_source(
    store: StrictBoundedReadStore,
    *,
    snapshot_id: str | None = None,
    attestation_materials: Sequence[AttestationMaterial],
    companyfacts_conversion: CompanyFactsLedgerConversion,
) -> AttestedQuerySnapshot:
    """Freshly compare external materials, rerun B3, and rejoin the B4 choices."""
    snapshot = verify_attested_query_snapshot(store, snapshot_id=snapshot_id)
    supplied = _material_map(attestation_materials)
    stored = {key: _thaw(value) for key, value in snapshot.attestations.items()}
    if set(supplied) != set(stored) or any(supplied[key] != stored[key] for key in stored):
        raise AttestedQuerySnapshotError("external attestation materials do not exactly match stored B3 records")
    if type(companyfacts_conversion) is not CompanyFactsLedgerConversion:
        raise AttestedQuerySnapshotError("companyfacts_conversion must be an exact CompanyFactsLedgerConversion")
    try:
        companyfacts_conversion.__post_init__()
    except (TypeError, ValueError) as exc:
        raise AttestedQuerySnapshotError(f"Company Facts conversion invariant failed: {exc}") from exc
    if _conversion_payload(companyfacts_conversion) != _conversion_payload(snapshot.companyfacts_conversion):
        raise AttestedQuerySnapshotError("external Company Facts conversion does not exactly match stored conversion")
    if companyfacts_conversion.receipt.to_dict() != _thaw(snapshot.manifest["companyfacts_conversion_receipt"]):
        raise AttestedQuerySnapshotError("external Company Facts conversion receipt does not exactly match stored receipt")
    binding_records, roots = _validated_bindings(
        base=snapshot.base_snapshot,
        conversion=companyfacts_conversion,
        records=stored,
        bindings=snapshot.bindings,
    )
    stored_bindings = _binding_payload([_thaw_binding(item, snapshot) for item in snapshot.bindings])
    if stored_bindings != _binding_payload(binding_records):
        raise AttestedQuerySnapshotError("fresh Company Facts conversion does not reproduce stored occurrence bindings")
    if _coverage_rows(roots, binding_records, _eligible_leaf_ids(snapshot.base_snapshot)) != [_thaw(item) for item in snapshot.cell_coverage]:
        raise AttestedQuerySnapshotError("fresh selected raw leaves do not reproduce stored cell coverage")
    return snapshot


def _thaw_binding(binding: AttestedOccurrenceBinding, snapshot: AttestedQuerySnapshot) -> dict[str, Any]:
    """Recover canonical stored binding projection without exposing it publicly."""
    # The canonical payload is re-read through the bounded storage path by the
    # caller's prior ``verify_attested_query_snapshot``.  Reconstructing this
    # compact projection from the sealed B3 record is enough for source-verify
    # equality, because it is also checked against the external conversion.
    record = snapshot.attestations[binding.attestation_id]
    match = next(item for item in record["company_facts"]["matches"] if item["match_id"] == binding.match_id)
    projection = match["projection"]
    return {
        **binding.to_dict(),
        "companyfacts": {
            "capture_id": record["company_facts"]["capture_id"], "manifest_id": record["company_facts"]["manifest_id"], "response_sha256": record["company_facts"]["response_sha256"],
            "cik": projection["cik"], "accession": projection["accession"], "taxonomy": match["taxonomy"], "concept": match["concept"], "unit": match["unit"], "entry_index": match["entry_index"],
            "start": projection["start"], "end": projection["end"], "value": projection["value"], "dimensions_known": False,
        },
    }


__all__ = [
    "ATTESTED_QUERY_SNAPSHOT_ID_PREFIX", "ATTESTED_QUERY_SNAPSHOT_POINTER_SCHEMA", "ATTESTED_QUERY_SNAPSHOT_POLICY_FINGERPRINT", "ATTESTED_QUERY_SNAPSHOT_POLICY_VERSION", "ATTESTED_QUERY_SNAPSHOT_PREFIX", "ATTESTED_QUERY_SNAPSHOT_PUBLICATION_CONTRACT", "ATTESTED_QUERY_SNAPSHOT_SCHEMA",
    "AttestationMaterial", "AttestedOccurrenceBinding", "AttestedQueryReceiptIndex", "AttestedQuerySnapshot", "AttestedQuerySnapshotArtifact", "AttestedQuerySnapshotError", "AttestedQuerySnapshotPointer", "PreparedAttestedQuerySnapshot",
    "load_attested_query_receipt_index", "load_attested_query_snapshot", "prepare_attested_query_snapshot", "publish_attested_query_snapshot", "reset_attested_query_receipt_index_cache", "verify_attested_query_snapshot", "verify_attested_query_snapshot_source",
]
