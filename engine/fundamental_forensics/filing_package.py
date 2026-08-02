"""Bounded, immutable offline SEC filing-package attestations.

This module deliberately does not fetch, store, or parse filing content.  It
commits the evidence an upstream archive lane has already retained: one exact
filing-manifest version, the stored ``index.json`` document and receipt, the
canonical archive-index payload, and an explicit outcome for every safe member
named by that index.  It therefore makes a narrow claim: inventory accounting,
not SEC-universe completeness, byte parsing, or XBRL semantics.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import hmac
import json
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .models import canonical_json, parse_utc, stable_id, utc_text
from .sec_document_spine import (
    ARCHIVE_RECEIPT_SCHEMA,
    FILING_MANIFEST_SCHEMA,
    FilingManifestError,
    HARD_MAX_ARCHIVE_DOCUMENT_BYTES,
    HARD_MAX_ARCHIVE_INDEX_MEMBERS,
    HARD_MAX_HTTP_METADATA_BYTES,
    archive_document_url,
    archive_index_url,
    canonical_cik,
    parse_json_int64,
    validate_manifest,
)


FILING_PACKAGE_SCHEMA = "fundamental_forensics.filing_package/v1"
FILING_PACKAGE_ID_PREFIX = "ffpkg_"
# These are admission limits for one offline attestation.  They are not a
# statement about the maximum size of a filing in the SEC archive.
HARD_MAX_FILING_PACKAGE_BYTES = 32 * 1024 * 1024
HARD_MAX_ARCHIVE_INDEX_PAYLOAD_BYTES = 8 * 1024 * 1024
HARD_MAX_ARCHIVE_INDEX_JSON_NODES = 250_000
HARD_MAX_ARCHIVE_INDEX_DEPTH = 48
HARD_MAX_MEMBER_BYTES = HARD_MAX_ARCHIVE_DOCUMENT_BYTES
HARD_MAX_RETAINED_MEMBER_BYTES = 2 * 1024 * 1024 * 1024
MAX_TEXT_BYTES = 16 * 1024
MAX_POLICY_TEXT_BYTES = 512

_PACKAGE_ID_RE = re.compile(r"^ffpkg_[a-f0-9]{64}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_RECEIPT_ID_RE = re.compile(r"^sec_archive_receipt_[a-f0-9]{64}$")
_DOCUMENT_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_MEMBER_STATES = frozenset({"stored", "missing", "not_requested", "rejected_by_policy"})
_PACKAGE_FIELDS = frozenset(
    {
        "schema",
        "package_id",
        "filing",
        "archive_index",
        "inventory",
        "coverage",
        "attestations",
        "assembly",
    }
)
_FILING_FIELDS = frozenset(
    {"manifest_schema", "cik", "accession", "filing_id", "manifest_id", "archive_index_url"}
)
_INDEX_FIELDS = frozenset(
    {
        "document",
        "raw_content_base64",
        "payload",
        "payload_sha256",
        "payload_byte_length",
    }
)
_DOCUMENT_FIELDS = frozenset(
    {
        "document_id",
        "document_name",
        "document_type",
        "sequence",
        "role",
        "archive_url",
        "availability",
        "content_sha256",
        "byte_length",
        "storage_key",
        "retrieval",
        "source_spans",
    }
)
_INVENTORY_FIELDS = frozenset(
    {
        "document_name",
        "document_id",
        "role",
        "archive_url",
        "state",
        "content_sha256",
        "byte_length",
        "storage_key",
        "retrieval",
        "policy_reason",
    }
)
_EVIDENCE_FIELDS = frozenset(
    {"state", "content_sha256", "byte_length", "storage_key", "retrieval", "policy_reason"}
)
_COVERAGE_FIELDS = frozenset(
    {
        "package_inventory_complete",
        "safe_archive_index_member_count",
        "stored_member_count",
        "missing_member_count",
        "not_requested_member_count",
        "rejected_by_policy_member_count",
        "all_index_members_receipted_as_stored",
        "all_filing_bytes_retained",
        "sec_universe_complete",
    }
)
_ATTESTATION_FIELDS = frozenset(
    {"archive_object_presence_attested", "xbrl_semantic_attested"}
)
_ASSEMBLY_FIELDS = frozenset({"assembled_at", "policy_profile", "policy_version"})
_RETRIEVED_RECEIPT_FIELDS = frozenset(
    {
        "schema",
        "receipt_id",
        "status",
        "document_id",
        "archive_url",
        "retrieved_at",
        "content_sha256",
        "byte_length",
        "storage_key",
        "http_etag",
        "http_last_modified",
    }
)
_MISSING_RECEIPT_FIELDS = frozenset(
    {"schema", "status", "document_id", "archive_url", "retrieved_at", "http_status", "reason"}
)


class FilingPackageError(ValueError):
    """A filing package cannot make its claimed offline attestation."""


def _strict_object(value: Any, *, field: str, required: frozenset[str]) -> dict[str, Any]:
    """Copy one exact-shape Mapping without trusting ``len`` or ``dict(value)``."""
    if not isinstance(value, Mapping):
        raise FilingPackageError(f"{field} must be an object")
    try:
        iterator = iter(value.items())
    except Exception as exc:  # noqa: BLE001 - hostile Mapping boundary.
        raise FilingPackageError(f"{field} cannot be iterated") from exc
    result: dict[str, Any] = {}
    for index in range(len(required) + 1):
        try:
            pair = next(iterator)
        except StopIteration:
            break
        except Exception as exc:  # noqa: BLE001 - hostile Mapping boundary.
            raise FilingPackageError(f"{field} iterator failed") from exc
        if index == len(required):
            raise FilingPackageError(f"{field} shape is invalid")
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise FilingPackageError(f"{field} iterator yielded an invalid entry")
        key, item = pair
        if not isinstance(key, str) or key not in required or key in result:
            raise FilingPackageError(f"{field} shape is invalid")
        result[key] = item
    if len(result) != len(required):
        raise FilingPackageError(f"{field} shape is invalid")
    return result


def _text(value: Any, *, field: str, maximum: int = MAX_TEXT_BYTES) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise FilingPackageError(f"{field} must be non-empty normalized text")
    try:
        if len(value.encode("utf-8")) > maximum:
            raise FilingPackageError(f"{field} exceeds bounded text length")
    except UnicodeError as exc:
        raise FilingPackageError(f"{field} is not valid UTF-8 text") from exc
    return value


def _nullable_text(
    value: Any,
    *,
    field: str,
    maximum: int = MAX_TEXT_BYTES,
) -> str | None:
    if value is None:
        return None
    return _text(value, field=field, maximum=maximum)


def _receipt_http_metadata(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or any(char in value for char in ("\x00", "\r", "\n")):
        raise FilingPackageError(f"{field} contains invalid HTTP header characters")
    try:
        if len(value.encode("utf-8")) > HARD_MAX_HTTP_METADATA_BYTES:
            raise FilingPackageError(f"{field} exceeds bounded text length")
    except UnicodeError as exc:
        raise FilingPackageError(f"{field} is not valid UTF-8 text") from exc
    return value


def _sha256(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise FilingPackageError(f"{field} must be lowercase SHA-256 hex")
    return value


def _length(value: Any, *, field: str, maximum: int = HARD_MAX_MEMBER_BYTES) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > maximum:
        raise FilingPackageError(f"{field} is outside the bounded byte range")
    return value


def _clock(value: Any, *, field: str) -> str:
    if not isinstance(value, (str, datetime)):
        raise FilingPackageError(f"{field} must be a UTC timestamp")
    try:
        parsed = parse_utc(value, field=field)
    except ValueError as exc:
        raise FilingPackageError(str(exc)) from exc
    if parsed is None:  # pragma: no cover - value is required above.
        raise FilingPackageError(f"{field} is required")
    return utc_text(parsed) or ""  # pragma: no cover - parsed is non-null.


def _safe_name(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise FilingPackageError(f"{field} is not a safe archive member name")
    parts = value.split("/")
    if (
        value.startswith("/")
        or "\\" in value
        or "\x00" in value
        or "?" in value
        or "#" in value
        or any(part in {"", ".", ".."} or not _DOCUMENT_SEGMENT_RE.fullmatch(part) for part in parts)
    ):
        raise FilingPackageError(f"{field} is not a safe archive member name")
    return value


def _storage_key(digest: str) -> str:
    return f"objects/sha256/{digest[:2]}/{digest}.bin.gz"


def _copy_json(value: Any, *, field: str, budget: list[int], depth: int = 0) -> Any:
    """Bound and copy JSON-native data; arbitrary Iterables are never accepted."""
    if depth > HARD_MAX_ARCHIVE_INDEX_DEPTH:
        raise FilingPackageError(f"{field} exceeds JSON nesting safety limit")
    budget[0] -= 1
    if budget[0] < 0:
        raise FilingPackageError(f"{field} exceeds JSON node safety limit")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value < -(1 << 63) or value > (1 << 63) - 1:
            raise FilingPackageError(f"{field} integer is outside signed-64-bit range")
        return value
    if isinstance(value, float):
        raise FilingPackageError(f"{field} cannot contain binary floats")
    if isinstance(value, str):
        try:
            if len(value.encode("utf-8")) > MAX_TEXT_BYTES:
                raise FilingPackageError(f"{field} string exceeds bounded text length")
        except UnicodeError as exc:
            raise FilingPackageError(f"{field} is not valid UTF-8 text") from exc
        return value
    if isinstance(value, Mapping):
        try:
            iterator = iter(value.items())
        except Exception as exc:  # noqa: BLE001 - hostile Mapping boundary.
            raise FilingPackageError(f"{field} cannot be iterated") from exc
        out: dict[str, Any] = {}
        for index in range(HARD_MAX_ARCHIVE_INDEX_JSON_NODES + 1):
            try:
                pair = next(iterator)
            except StopIteration:
                break
            except Exception as exc:  # noqa: BLE001 - hostile Mapping boundary.
                raise FilingPackageError(f"{field} iterator failed") from exc
            if index == HARD_MAX_ARCHIVE_INDEX_JSON_NODES:
                raise FilingPackageError(f"{field} has too many object entries")
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise FilingPackageError(f"{field} iterator yielded an invalid entry")
            key, item = pair
            if not isinstance(key, str) or key in out:
                raise FilingPackageError(f"{field} object keys are invalid")
            try:
                if len(key.encode("utf-8")) > MAX_TEXT_BYTES:
                    raise FilingPackageError(f"{field} object key exceeds bounded text length")
            except UnicodeError as exc:
                raise FilingPackageError(f"{field} object key is not valid UTF-8 text") from exc
            out[key] = _copy_json(item, field=field, budget=budget, depth=depth + 1)
        return out
    # Exact list is intentional: a generator or a clever Sequence must not be
    # allowed to sidestep an item cap during archive-index admission.
    if type(value) is list:
        if len(value) > HARD_MAX_ARCHIVE_INDEX_JSON_NODES:
            raise FilingPackageError(f"{field} has too many array entries")
        return [_copy_json(item, field=field, budget=budget, depth=depth + 1) for item in value]
    raise FilingPackageError(f"{field} must contain JSON-native values")


def _canonical_payload(value: Any) -> tuple[dict[str, Any], bytes]:
    copied = _copy_json(
        value,
        field="archive index payload",
        budget=[HARD_MAX_ARCHIVE_INDEX_JSON_NODES],
    )
    if not isinstance(copied, dict):
        raise FilingPackageError("archive index payload must be an object")
    payload = canonical_json(copied).encode("utf-8")
    if len(payload) > HARD_MAX_ARCHIVE_INDEX_PAYLOAD_BYTES:
        raise FilingPackageError("archive index payload exceeds byte safety limit")
    return copied, payload


def _archive_index_from_bytes(
    content: Any,
    *,
    document: Mapping[str, Any],
) -> tuple[dict[str, Any], bytes]:
    """Verify and strictly parse the exact retained SEC ``index.json`` bytes."""
    if not isinstance(content, bytes):
        raise FilingPackageError("archive index content must be bytes")
    if len(content) > HARD_MAX_ARCHIVE_INDEX_PAYLOAD_BYTES:
        raise FilingPackageError("archive index content exceeds byte safety limit")
    if (
        len(content) != document["byte_length"]
        or not hmac.compare_digest(sha256(content).hexdigest(), document["content_sha256"])
    ):
        raise FilingPackageError(
            "archive index content does not match the retained document receipt"
        )

    def reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, item in pairs:
            if key in output:
                raise FilingPackageError(f"duplicate archive index JSON key: {key}")
            output[key] = item
        return output

    def reject_constant(value: str) -> None:
        raise FilingPackageError(f"non-finite archive index JSON constant: {value}")

    def reject_float(value: str) -> None:
        raise FilingPackageError(f"archive index JSON cannot contain binary float: {value}")

    try:
        decoded = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=reject_pairs,
            parse_constant=reject_constant,
            parse_float=reject_float,
            parse_int=parse_json_int64,
        )
    except FilingPackageError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise FilingPackageError("archive index content is not strict UTF-8 JSON") from exc
    return _canonical_payload(decoded)


def _raw_content_base64(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def _raw_content_from_base64(value: Any) -> bytes:
    maximum = 4 * ((HARD_MAX_ARCHIVE_INDEX_PAYLOAD_BYTES + 2) // 3)
    if not isinstance(value, str) or len(value) > maximum:
        raise FilingPackageError("archive index raw-content witness exceeds byte safety limit")
    try:
        encoded = value.encode("ascii")
        content = base64.b64decode(encoded, validate=True)
    except (UnicodeError, ValueError) as exc:
        raise FilingPackageError("archive index raw-content witness is not canonical base64") from exc
    if _raw_content_base64(content) != value:
        raise FilingPackageError("archive index raw-content witness is not canonical base64")
    if len(content) > HARD_MAX_ARCHIVE_INDEX_PAYLOAD_BYTES:
        raise FilingPackageError("archive index raw-content witness exceeds byte safety limit")
    return content


def _inventory_names(payload: Mapping[str, Any]) -> tuple[str, ...]:
    directory = payload.get("directory")
    if not isinstance(directory, dict):
        raise FilingPackageError("archive index payload directory must be an object")
    items = directory.get("item")
    if type(items) is not list:
        raise FilingPackageError("archive index payload directory.item must be an array")
    if len(items) > HARD_MAX_ARCHIVE_INDEX_MEMBERS:
        raise FilingPackageError("archive index payload exceeds member safety limit")
    names: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise FilingPackageError(f"archive index member {index} must be an object")
        name = _safe_name(item.get("name"), field=f"archive index member {index}.name")
        if name in seen:
            raise FilingPackageError(f"duplicate archive index member name: {name}")
        seen.add(name)
        names.append(name)
    return tuple(sorted(names))


def _filing_binding(value: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    # Copy first so validation never calls ``get`` or iterates an unbounded
    # caller-owned Mapping.  The filing manifest itself remains authoritative.
    copied, encoded = _canonical_payload(value)
    if len(encoded) > HARD_MAX_ARCHIVE_INDEX_PAYLOAD_BYTES:
        raise FilingPackageError("filing manifest exceeds byte safety limit")
    try:
        validate_manifest(copied)
    except FilingManifestError as exc:
        raise FilingPackageError(f"filing manifest is invalid: {exc}") from exc
    issuer = copied["issuer"]
    filing = copied["filing"]
    cik = canonical_cik(issuer["cik"])
    accession = filing["accession"]
    binding = {
        "manifest_schema": FILING_MANIFEST_SCHEMA,
        "cik": cik,
        "accession": accession,
        "filing_id": copied["filing_id"],
        "manifest_id": copied["manifest_id"],
        "archive_index_url": archive_index_url(cik, accession),
    }
    return copied, binding


def _expected_document(
    manifest: Mapping[str, Any], *, cik: str, accession: str, name: str
) -> tuple[str, str]:
    matches = [document for document in manifest["documents"] if document["document_name"] == name]
    if len(matches) > 1:
        raise FilingPackageError(f"filing manifest has ambiguous archive member: {name}")
    if matches:
        document = matches[0]
        return str(document["document_id"]), str(document["role"])
    return stable_id("sec_document", cik, accession, "archive", name), "archive"


def _retrieved_receipt(
    value: Any,
    *,
    field: str,
    document_id: str,
    archive_url: str,
    digest: str,
    length: int,
    storage_key: str,
) -> dict[str, Any]:
    receipt = _strict_object(value, field=field, required=_RETRIEVED_RECEIPT_FIELDS)
    if receipt["schema"] != ARCHIVE_RECEIPT_SCHEMA or receipt["status"] != "retrieved":
        raise FilingPackageError(f"{field} is not a retrieved SEC archive receipt")
    if receipt["document_id"] != document_id or receipt["archive_url"] != archive_url:
        raise FilingPackageError(f"{field} does not bind the expected archive document")
    if (
        _sha256(receipt["content_sha256"], field=f"{field}.content_sha256") != digest
        or _length(receipt["byte_length"], field=f"{field}.byte_length") != length
        or receipt["storage_key"] != storage_key
    ):
        raise FilingPackageError(f"{field} does not bind its stored bytes")
    if storage_key != _storage_key(digest):
        raise FilingPackageError(f"{field} storage key does not bind its digest")
    retrieved_at = _clock(receipt["retrieved_at"], field=f"{field}.retrieved_at")
    if receipt["retrieved_at"] != retrieved_at:
        raise FilingPackageError(f"{field}.retrieved_at is not canonical UTC")
    etag = _receipt_http_metadata(receipt["http_etag"], field=f"{field}.http_etag")
    last_modified = _receipt_http_metadata(
        receipt["http_last_modified"], field=f"{field}.http_last_modified"
    )
    body = {
        "schema": ARCHIVE_RECEIPT_SCHEMA,
        "status": "retrieved",
        "document_id": document_id,
        "archive_url": archive_url,
        "retrieved_at": retrieved_at,
        "content_sha256": digest,
        "byte_length": length,
        "storage_key": storage_key,
        "http_etag": etag,
        "http_last_modified": last_modified,
    }
    receipt_id = receipt["receipt_id"]
    expected_id = stable_id("sec_archive_receipt", body)
    if not isinstance(receipt_id, str) or not _RECEIPT_ID_RE.fullmatch(receipt_id) or not hmac.compare_digest(receipt_id, expected_id):
        raise FilingPackageError(f"{field} identity mismatch")
    return {"receipt_id": receipt_id, **body}


def _missing_receipt(value: Any, *, field: str, document_id: str, archive_url: str) -> dict[str, Any]:
    receipt = _strict_object(value, field=field, required=_MISSING_RECEIPT_FIELDS)
    if receipt["schema"] != ARCHIVE_RECEIPT_SCHEMA or receipt["status"] != "missing":
        raise FilingPackageError(f"{field} is not a missing SEC archive receipt")
    if receipt["document_id"] != document_id or receipt["archive_url"] != archive_url:
        raise FilingPackageError(f"{field} does not bind the expected archive document")
    retrieved_at = _clock(receipt["retrieved_at"], field=f"{field}.retrieved_at")
    if receipt["retrieved_at"] != retrieved_at:
        raise FilingPackageError(f"{field}.retrieved_at is not canonical UTC")
    status = receipt["http_status"]
    if isinstance(status, bool) or status != 404:
        raise FilingPackageError(f"{field}.http_status must be the observed SEC 404")
    reason = _text(receipt["reason"], field=f"{field}.reason")
    if reason != "sec_archive_document_missing":
        raise FilingPackageError(f"{field}.reason is not the canonical missing-document reason")
    return {
        "schema": ARCHIVE_RECEIPT_SCHEMA,
        "status": "missing",
        "document_id": document_id,
        "archive_url": archive_url,
        "retrieved_at": retrieved_at,
        "http_status": status,
        "reason": reason,
    }


def _archive_index_document(value: Any, *, cik: str, accession: str) -> dict[str, Any]:
    document = _strict_object(value, field="archive index document", required=_DOCUMENT_FIELDS)
    name = _safe_name(document["document_name"], field="archive index document.document_name")
    expected_url = archive_index_url(cik, accession)
    expected_id = stable_id("sec_document", cik, accession, "archive", "index.json")
    if (
        name != "index.json"
        or document["role"] != "archive"
        or document["document_id"] != expected_id
        or document["archive_url"] != expected_url
        or document["availability"] != "stored"
    ):
        raise FilingPackageError("archive index document does not bind the filing index.json")
    document_type = _nullable_text(document["document_type"], field="archive index document.document_type")
    sequence = _nullable_text(document["sequence"], field="archive index document.sequence")
    digest = _sha256(document["content_sha256"], field="archive index document.content_sha256")
    length = _length(
        document["byte_length"],
        field="archive index document.byte_length",
        maximum=HARD_MAX_ARCHIVE_INDEX_PAYLOAD_BYTES,
    )
    storage_key = document["storage_key"]
    if not isinstance(storage_key, str) or storage_key != _storage_key(digest):
        raise FilingPackageError("archive index document storage_key does not bind its digest")
    receipt = _retrieved_receipt(
        document["retrieval"],
        field="archive index document.retrieval",
        document_id=expected_id,
        archive_url=expected_url,
        digest=digest,
        length=length,
        storage_key=storage_key,
    )
    expected_span = {
        "span_id": stable_id("sec_span", expected_id, f"bytes:0-{length}", digest),
        "locator_type": "byte_range",
        "locator": f"bytes:0-{length}",
        "text_sha256": digest,
    }
    if document["source_spans"] != [expected_span]:
        raise FilingPackageError("archive index document must retain its root source span")
    return {
        "document_id": expected_id,
        "document_name": "index.json",
        "document_type": document_type,
        "sequence": sequence,
        "role": "archive",
        "archive_url": expected_url,
        "availability": "stored",
        "content_sha256": digest,
        "byte_length": length,
        "storage_key": storage_key,
        "retrieval": receipt,
        "source_spans": [expected_span],
    }


def _evidence_input(value: Any, *, name: str, field: str) -> dict[str, Any]:
    if isinstance(value, str):
        return {
            "state": value,
            "content_sha256": None,
            "byte_length": None,
            "storage_key": None,
            "retrieval": None,
            "policy_reason": None,
        }
    return _strict_object(value, field=field, required=_EVIDENCE_FIELDS)


def _member_inputs(value: Any) -> dict[str, dict[str, Any]]:
    """Normalize either a name-keyed Mapping or exact-list member evidence."""
    out: dict[str, dict[str, Any]] = {}
    if isinstance(value, Mapping):
        try:
            iterator = iter(value.items())
        except Exception as exc:  # noqa: BLE001 - hostile Mapping boundary.
            raise FilingPackageError("member states cannot be iterated") from exc
        for index in range(HARD_MAX_ARCHIVE_INDEX_MEMBERS + 1):
            try:
                pair = next(iterator)
            except StopIteration:
                break
            except Exception as exc:  # noqa: BLE001 - hostile Mapping boundary.
                raise FilingPackageError("member states iterator failed") from exc
            if index == HARD_MAX_ARCHIVE_INDEX_MEMBERS:
                raise FilingPackageError("member states exceed member safety limit")
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise FilingPackageError("member states iterator yielded an invalid entry")
            raw_name, raw_evidence = pair
            name = _safe_name(raw_name, field="member state name")
            if name in out:
                raise FilingPackageError(f"duplicate member state: {name}")
            out[name] = _evidence_input(raw_evidence, name=name, field=f"member state {name}")
        return out
    if type(value) is not list:
        raise FilingPackageError("member states must be a mapping or an array")
    if len(value) > HARD_MAX_ARCHIVE_INDEX_MEMBERS:
        raise FilingPackageError("member states exceed member safety limit")
    for index, raw in enumerate(value):
        fields = _strict_object(
            raw,
            field=f"member state {index}",
            required=frozenset({"document_name", *_EVIDENCE_FIELDS}),
        )
        name = _safe_name(fields.pop("document_name"), field=f"member state {index}.document_name")
        if name in out:
            raise FilingPackageError(f"duplicate member state: {name}")
        out[name] = fields
    return out


def _inventory_item(
    *,
    evidence: Mapping[str, Any],
    manifest: Mapping[str, Any],
    cik: str,
    accession: str,
    name: str,
    final: bool,
) -> dict[str, Any]:
    document_id, role = _expected_document(manifest, cik=cik, accession=accession, name=name)
    archive_url = archive_document_url(cik, accession, name)
    if final:
        raw = _strict_object(evidence, field=f"inventory {name}", required=_INVENTORY_FIELDS)
        if (
            raw["document_name"] != name
            or raw["document_id"] != document_id
            or raw["role"] != role
            or raw["archive_url"] != archive_url
        ):
            raise FilingPackageError(f"inventory {name} does not bind its archive member")
        evidence = {key: raw[key] for key in _EVIDENCE_FIELDS}
    else:
        evidence = _strict_object(evidence, field=f"member state {name}", required=_EVIDENCE_FIELDS)
    state = evidence["state"]
    if not isinstance(state, str) or state not in _MEMBER_STATES:
        raise FilingPackageError(f"inventory {name} has invalid state")
    digest = evidence["content_sha256"]
    length = evidence["byte_length"]
    storage_key = evidence["storage_key"]
    retrieval = evidence["retrieval"]
    reason = evidence["policy_reason"]
    if state == "stored":
        digest = _sha256(digest, field=f"inventory {name}.content_sha256")
        length = _length(length, field=f"inventory {name}.byte_length")
        if not isinstance(storage_key, str) or storage_key != _storage_key(digest):
            raise FilingPackageError(f"inventory {name} storage_key does not bind digest")
        receipt = _retrieved_receipt(
            retrieval,
            field=f"inventory {name}.retrieval",
            document_id=document_id,
            archive_url=archive_url,
            digest=digest,
            length=length,
            storage_key=storage_key,
        )
        if reason is not None:
            raise FilingPackageError(f"stored inventory {name} cannot carry a policy reason")
    elif state == "missing":
        if any(item is not None for item in (digest, length, storage_key, reason)):
            raise FilingPackageError(f"missing inventory {name} cannot claim stored bytes or policy")
        receipt = _missing_receipt(
            retrieval,
            field=f"inventory {name}.retrieval",
            document_id=document_id,
            archive_url=archive_url,
        )
        digest = length = storage_key = None
    else:
        if any(item is not None for item in (digest, length, storage_key, retrieval)):
            raise FilingPackageError(f"unrequested inventory {name} cannot carry retrieval evidence")
        if state == "rejected_by_policy":
            reason = _text(reason, field=f"inventory {name}.policy_reason", maximum=MAX_POLICY_TEXT_BYTES)
        elif reason is not None:
            raise FilingPackageError(f"not-requested inventory {name} cannot carry a policy reason")
        receipt = None
        digest = length = storage_key = None
    return {
        "document_name": name,
        "document_id": document_id,
        "role": role,
        "archive_url": archive_url,
        "state": state,
        "content_sha256": digest,
        "byte_length": length,
        "storage_key": storage_key,
        "retrieval": receipt,
        "policy_reason": reason,
    }


def _coverage(inventory: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = {state: 0 for state in _MEMBER_STATES}
    retained = 0
    for item in inventory:
        state = item["state"]
        counts[state] += 1
        if state == "stored":
            retained += int(item["byte_length"])
    if retained > HARD_MAX_RETAINED_MEMBER_BYTES:
        raise FilingPackageError("filing package retained-byte total exceeds safety limit")
    return {
        "package_inventory_complete": True,
        "safe_archive_index_member_count": len(inventory),
        "stored_member_count": counts["stored"],
        "missing_member_count": counts["missing"],
        "not_requested_member_count": counts["not_requested"],
        "rejected_by_policy_member_count": counts["rejected_by_policy"],
        "all_index_members_receipted_as_stored": all(
            item["state"] == "stored" for item in inventory
        ),
        # A content-addressed receipt is not proof that its external object is
        # still present.  B-B3 can raise this only after a store-backed sealed
        # attestation; the unsigned v1 package must remain honest and false.
        "all_filing_bytes_retained": False,
        "sec_universe_complete": False,
    }


def _package_id(record: Mapping[str, Any]) -> str:
    body = dict(record)
    body.pop("package_id", None)
    return FILING_PACKAGE_ID_PREFIX + sha256(canonical_json(body).encode("utf-8")).hexdigest()


def filing_package_id_for(record: Mapping[str, Any]) -> str:
    """Return the content ID that commits to every package field except its ID."""
    return _package_id(record)


def _normalise_record(value: Any) -> dict[str, Any]:
    record = _strict_object(value, field="filing package", required=_PACKAGE_FIELDS)
    if record["schema"] != FILING_PACKAGE_SCHEMA:
        raise FilingPackageError("unsupported filing package schema")
    filing = _strict_object(record["filing"], field="filing package filing", required=_FILING_FIELDS)
    if filing["manifest_schema"] != FILING_MANIFEST_SCHEMA:
        raise FilingPackageError("filing package source manifest schema is invalid")
    try:
        cik = canonical_cik(filing["cik"])
        accession = _text(filing["accession"], field="filing package accession")
        expected_index_url = archive_index_url(cik, accession)
    except (FilingManifestError, TypeError, ValueError) as exc:
        raise FilingPackageError("filing package filing binding is invalid") from exc
    if (
        filing["archive_index_url"] != expected_index_url
        or not isinstance(filing["filing_id"], str)
        or not isinstance(filing["manifest_id"], str)
        or not filing["manifest_id"].startswith("ffsec_manifest_")
    ):
        raise FilingPackageError("filing package filing binding is invalid")
    # ``validate_manifest`` already verified the source identity at build time.
    # A package only persists its manifest content ID, so check the identifier
    # shape here without pretending the entire source manifest is embedded.
    if not re.fullmatch(r"ffsec_manifest_[a-f0-9]{64}", filing["manifest_id"]):
        raise FilingPackageError("filing package manifest_id is invalid")
    if filing["filing_id"] != stable_id("sec_filing", cik, accession):
        raise FilingPackageError("filing package filing_id is invalid")
    canonical_filing = {
        "manifest_schema": FILING_MANIFEST_SCHEMA,
        "cik": cik,
        "accession": accession,
        "filing_id": filing["filing_id"],
        "manifest_id": filing["manifest_id"],
        "archive_index_url": expected_index_url,
    }
    index = _strict_object(record["archive_index"], field="filing package archive_index", required=_INDEX_FIELDS)
    document = _archive_index_document(index["document"], cik=cik, accession=accession)
    raw_content_base64 = index["raw_content_base64"]
    raw_content = _raw_content_from_base64(raw_content_base64)
    verified_payload, verified_payload_bytes = _archive_index_from_bytes(
        raw_content,
        document=document,
    )
    supplied_payload, supplied_payload_bytes = _canonical_payload(index["payload"])
    if supplied_payload != verified_payload or supplied_payload_bytes != verified_payload_bytes:
        raise FilingPackageError(
            "archive index projection does not derive from its raw-content witness"
        )
    payload = verified_payload
    payload_bytes = verified_payload_bytes
    payload_digest = sha256(payload_bytes).hexdigest()
    if (
        index["payload_sha256"] != payload_digest
        or index["payload_byte_length"] != len(payload_bytes)
    ):
        raise FilingPackageError("archive index canonical payload digest or byte length mismatch")
    names = _inventory_names(payload)
    raw_inventory = record["inventory"]
    if type(raw_inventory) is not list or len(raw_inventory) > HARD_MAX_ARCHIVE_INDEX_MEMBERS:
        raise FilingPackageError("filing package inventory is not a bounded array")
    inventory: list[dict[str, Any]] = []
    provided_inventory: list[dict[str, Any]] = []
    seen: set[str] = set()
    # The source manifest is represented here by its immutable content ID, not
    # embedded in full.  Persisted member role lets restore recompute document
    # identity without consulting mutable source state.
    for raw in raw_inventory:
        raw_copy = _strict_object(raw, field="filing package inventory", required=_INVENTORY_FIELDS)
        name = _safe_name(raw_copy["document_name"], field="filing package inventory.document_name")
        if name in seen:
            raise FilingPackageError(f"duplicate filing package inventory member: {name}")
        seen.add(name)
        role = raw_copy["role"]
        if not isinstance(role, str) or role not in {"primary", "exhibit", "archive"}:
            raise FilingPackageError(f"inventory {name} has invalid document role")
        expected_id = stable_id("sec_document", cik, accession, role, name)
        if raw_copy["document_id"] != expected_id:
            raise FilingPackageError(f"inventory {name} document_id does not bind role and member name")
        provided_inventory.append(raw_copy)
        inventory.append(
            _inventory_item(
                evidence=raw_copy,
                manifest={"documents": [{"document_name": name, "document_id": expected_id, "role": role}]},
                cik=cik,
                accession=accession,
                name=name,
                final=True,
            )
        )
    inventory.sort(key=lambda item: item["document_name"])
    if tuple(item["document_name"] for item in inventory) != names:
        raise FilingPackageError("filing package inventory does not account for archive index members")
    if provided_inventory != inventory:
        raise FilingPackageError("filing package inventory is not in canonical order or form")
    coverage = _strict_object(record["coverage"], field="filing package coverage", required=_COVERAGE_FIELDS)
    expected_coverage = _coverage(inventory)
    if coverage != expected_coverage:
        raise FilingPackageError("filing package coverage does not match inventory states")
    attestations = _strict_object(record["attestations"], field="filing package attestations", required=_ATTESTATION_FIELDS)
    if (
        attestations["archive_object_presence_attested"] is not False
        or attestations["xbrl_semantic_attested"] is not False
    ):
        raise FilingPackageError("filing package cannot claim sealed archive or XBRL attestation")
    assembly = _strict_object(record["assembly"], field="filing package assembly", required=_ASSEMBLY_FIELDS)
    assembled_at = _clock(assembly["assembled_at"], field="filing package assembly.assembled_at")
    if assembly["assembled_at"] != assembled_at:
        raise FilingPackageError("filing package assembly clock is not canonical UTC")
    canonical_assembly = {
        "assembled_at": assembled_at,
        "policy_profile": _text(assembly["policy_profile"], field="filing package policy_profile", maximum=MAX_POLICY_TEXT_BYTES),
        "policy_version": _text(assembly["policy_version"], field="filing package policy_version", maximum=MAX_POLICY_TEXT_BYTES),
    }
    evidence_clocks = [document["retrieval"]["retrieved_at"]]
    evidence_clocks.extend(
        item["retrieval"]["retrieved_at"]
        for item in inventory
        if item["retrieval"] is not None
    )
    assembled_clock = parse_utc(assembled_at, field="filing package assembly.assembled_at")
    latest_evidence_clock = max(
        parse_utc(value, field="filing package evidence retrieved_at")
        for value in evidence_clocks
    )
    if assembled_clock is None or latest_evidence_clock is None:  # pragma: no cover
        raise FilingPackageError("filing package evidence clocks are required")
    if assembled_clock < latest_evidence_clock:
        raise FilingPackageError("filing package cannot be assembled before its evidence")
    result = {
        "schema": FILING_PACKAGE_SCHEMA,
        "package_id": record["package_id"],
        "filing": canonical_filing,
        "archive_index": {
            "document": document,
            "raw_content_base64": raw_content_base64,
            "payload": payload,
            "payload_sha256": payload_digest,
            "payload_byte_length": len(payload_bytes),
        },
        "inventory": inventory,
        "coverage": expected_coverage,
        "attestations": {
            "archive_object_presence_attested": False,
            "xbrl_semantic_attested": False,
        },
        "assembly": canonical_assembly,
    }
    expected_id = _package_id(result)
    actual_id = result["package_id"]
    if not isinstance(actual_id, str) or not _PACKAGE_ID_RE.fullmatch(actual_id) or not hmac.compare_digest(actual_id, expected_id):
        raise FilingPackageError("filing package identity mismatch")
    encoded = canonical_json(result).encode("utf-8")
    if len(encoded) > HARD_MAX_FILING_PACKAGE_BYTES:
        raise FilingPackageError("filing package exceeds byte safety limit")
    return result


def validate_filing_package(value: Mapping[str, Any]) -> None:
    """Validate a canonical package mapping and every evidence binding in it."""
    _normalise_record(value)


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class FilingPackage:
    """An immutable in-memory view of one verified filing-package manifest."""

    _record: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "_record", _freeze(_normalise_record(self._record)))

    @property
    def package_id(self) -> str:
        return str(self._record["package_id"])

    @property
    def content_id(self) -> str:
        """Alias emphasizing that package identity commits the entire manifest."""
        return self.package_id

    @property
    def manifest(self) -> Mapping[str, Any]:
        """A read-only view of the verified package manifest."""
        return self._record

    def to_dict(self) -> dict[str, Any]:
        return _thaw(self._record)

    def to_json_bytes(self) -> bytes:
        return canonical_json(self.to_dict()).encode("utf-8")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FilingPackage":
        return cls(value)

    @classmethod
    def from_json_bytes(cls, content: bytes) -> "FilingPackage":
        return filing_package_from_json_bytes(content)


def build_filing_package(
    filing_manifest: Mapping[str, Any],
    archive_index_document: Mapping[str, Any],
    archive_index_content: bytes,
    member_states: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    assembled_at: str | datetime,
    policy_profile: str,
    policy_version: str,
) -> FilingPackage:
    """Assemble one canonical package from already-retained offline evidence.

    ``member_states`` is either a safe-name-keyed mapping of exact evidence
    objects (or a bare state string for ``not_requested``), or an array whose
    entries also contain ``document_name``.  Each safe ``directory.item`` name
    in the archive index must appear exactly once; no caller can silently omit
    an inconvenient member.
    """
    manifest, filing = _filing_binding(filing_manifest)
    cik = filing["cik"]
    accession = filing["accession"]
    index_document = _archive_index_document(archive_index_document, cik=cik, accession=accession)
    payload, payload_bytes = _archive_index_from_bytes(
        archive_index_content,
        document=index_document,
    )
    names = _inventory_names(payload)
    evidence_by_name = _member_inputs(member_states)
    if set(evidence_by_name) != set(names):
        raise FilingPackageError("member states must account for exactly the archive index inventory")
    inventory = [
        _inventory_item(
            evidence=evidence_by_name[name],
            manifest=manifest,
            cik=cik,
            accession=accession,
            name=name,
            final=False,
        )
        for name in names
    ]
    record: dict[str, Any] = {
        "schema": FILING_PACKAGE_SCHEMA,
        "package_id": "",
        "filing": filing,
        "archive_index": {
            "document": index_document,
            "raw_content_base64": _raw_content_base64(archive_index_content),
            "payload": payload,
            "payload_sha256": sha256(payload_bytes).hexdigest(),
            "payload_byte_length": len(payload_bytes),
        },
        "inventory": inventory,
        "coverage": _coverage(inventory),
        "attestations": {
            "archive_object_presence_attested": False,
            "xbrl_semantic_attested": False,
        },
        "assembly": {
            "assembled_at": _clock(assembled_at, field="assembled_at"),
            "policy_profile": _text(policy_profile, field="policy_profile", maximum=MAX_POLICY_TEXT_BYTES),
            "policy_version": _text(policy_version, field="policy_version", maximum=MAX_POLICY_TEXT_BYTES),
        },
    }
    record["package_id"] = _package_id(record)
    return FilingPackage.from_dict(record)


def filing_package_json_bytes(value: FilingPackage | Mapping[str, Any]) -> bytes:
    """Validate and encode a package in its sole canonical JSON representation."""
    if isinstance(value, FilingPackage):
        return value.to_json_bytes()
    return FilingPackage.from_dict(value).to_json_bytes()


def filing_package_from_json_bytes(content: bytes) -> FilingPackage:
    """Restore only canonical UTF-8 JSON, rejecting duplicate keys and NaN."""
    if not isinstance(content, bytes):
        raise FilingPackageError("filing package JSON must be bytes")
    if len(content) > HARD_MAX_FILING_PACKAGE_BYTES:
        raise FilingPackageError("filing package JSON exceeds byte safety limit")

    def reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, item in pairs:
            if key in output:
                raise FilingPackageError(f"duplicate JSON key: {key}")
            output[key] = item
        return output

    def reject_constant(value: str) -> None:
        raise FilingPackageError(f"non-finite JSON constant: {value}")

    try:
        decoded = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=reject_pairs,
            parse_constant=reject_constant,
            parse_int=parse_json_int64,
        )
    except FilingPackageError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise FilingPackageError("filing package JSON is not UTF-8 JSON") from exc
    if not isinstance(decoded, Mapping):
        raise FilingPackageError("filing package JSON must be an object")
    package = FilingPackage.from_dict(decoded)
    if package.to_json_bytes() != content:
        raise FilingPackageError("filing package JSON is not canonically encoded")
    return package


__all__ = [
    "ARCHIVE_RECEIPT_SCHEMA",
    "FILING_PACKAGE_ID_PREFIX",
    "FILING_PACKAGE_SCHEMA",
    "HARD_MAX_ARCHIVE_INDEX_MEMBERS",
    "HARD_MAX_ARCHIVE_INDEX_PAYLOAD_BYTES",
    "HARD_MAX_FILING_PACKAGE_BYTES",
    "FilingPackage",
    "FilingPackageError",
    "build_filing_package",
    "filing_package_from_json_bytes",
    "filing_package_id_for",
    "filing_package_json_bytes",
    "validate_filing_package",
]
