"""Receipt-bound, immutable wrappers for strict offline SEC filing parses.

This module is intentionally a small authority boundary.  The low-level parser
owns XML/iXBRL admission and structural extraction; this layer proves that one
such parse was run against exactly one stored member of one immutable filing
package.  It has no storage, network, raw-ledger, API, or UI dependency.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import hmac
import importlib
import json
import re
from types import MappingProxyType
from typing import Any, Mapping

from .filing_package import (
    FILING_PACKAGE_SCHEMA,
    HARD_MAX_MEMBER_BYTES,
    FilingPackage,
    FilingPackageError,
)
from .models import canonical_json, parse_utc, stable_id, utc_text
from .sec_document_spine import ARCHIVE_RECEIPT_SCHEMA, archive_document_url, archive_index_url, canonical_cik, parse_json_int64


FFXBRL_SCHEMA = "fundamental_forensics.ixbrl_extraction/v1"
FFXBRL_ID_PREFIX = "ffxbrl_"
# ``ffxbrl`` adds receipt-scoped identities and references to every parser
# record.  It is therefore deliberately a materially smaller admission
# envelope than a generic XML parser.  Do not loosen one of these values in
# isolation: `_parser_api` proves that the selected parser profile has been
# configured no wider than this wrapper can faithfully seal.
HARD_MAX_FFXBRL_BYTES = 64 * 1024 * 1024
HARD_MAX_PARSER_OUTPUT_BYTES = 24 * 1024 * 1024
HARD_MAX_JSON_NODES = 1_200_000
HARD_MAX_JSON_DEPTH = 64
HARD_MAX_JSON_TOKENS = 1_500_000
HARD_MAX_JSON_SCALARS = 900_000
HARD_MAX_JSON_OBJECT_KEYS = 600_000
HARD_MAX_JSON_DECODED_STRING_BYTES = 48 * 1024 * 1024
HARD_MAX_JSON_NUMBER_TOKEN_BYTES = 128
MAX_TEXT_BYTES = 1 * 1024 * 1024
MAX_METADATA_BYTES = 16 * 1024
HARD_MAX_JSON_STRING_TOKEN_BYTES = MAX_TEXT_BYTES
FFXBRL_LIMITS = MappingProxyType(
    {
        "max_contexts": 5_000,
        "max_units": 2_000,
        "max_continuations": 10_000,
        "max_facts": 10_000,
        "max_continuation_chain": 16,
        "max_diagnostics": 15_000,
        "max_parser_output_bytes": HARD_MAX_PARSER_OUTPUT_BYTES,
        "max_artifact_bytes": HARD_MAX_FFXBRL_BYTES,
        "max_json_nodes": HARD_MAX_JSON_NODES,
        "max_json_depth": HARD_MAX_JSON_DEPTH,
    }
)
_PARSER_ENVELOPE_FIELDS = MappingProxyType(
    {
        "max_contexts": FFXBRL_LIMITS["max_contexts"],
        "max_units": FFXBRL_LIMITS["max_units"],
        "max_continuations": FFXBRL_LIMITS["max_continuations"],
        "max_facts": FFXBRL_LIMITS["max_facts"],
        "max_continuation_chain": FFXBRL_LIMITS["max_continuation_chain"],
        "max_output_bytes": HARD_MAX_PARSER_OUTPUT_BYTES,
    }
)

_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_PACKAGE_ID_RE = re.compile(r"^ffpkg_[a-f0-9]{64}$")
_RESULT_ID_RE = re.compile(r"^ffxbrl_[a-f0-9]{64}$")
_RECEIPT_ID_RE = re.compile(r"^sec_archive_receipt_[a-f0-9]{64}$")
_MEMBER_NAME_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
_TOP_FIELDS = frozenset(
    {
        "schema",
        "extraction_id",
        "source",
        "parser",
        "extraction",
        "document",
        "contexts",
        "units",
        "continuations",
        "facts",
        "diagnostics",
        "coverage",
        "nonclaims",
    }
)
_SOURCE_FIELDS = frozenset({"package_schema", "package_id", "filing", "member"})
_FILING_FIELDS = frozenset(
    {"manifest_schema", "cik", "accession", "filing_id", "manifest_id", "archive_index_url"}
)
_MEMBER_FIELDS = frozenset(
    {
        "document_name",
        "document_id",
        "role",
        "archive_url",
        "content_sha256",
        "byte_length",
        "storage_key",
        "retrieval",
    }
)
_RECEIPT_FIELDS = frozenset(
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
_PARSER_FIELDS = frozenset(
    {
        "profile",
        "version",
        "algorithm_fingerprint",
        "library",
        "library_version",
        "xml_library_version",
        "transform_registry",
    }
)
_EXTRACTION_FIELDS = frozenset({"computed_at", "parser_schema"})
_LOW_LEVEL_OUTPUT_FIELDS = frozenset(
    {
        "schema",
        "parser",
        "source",
        "document",
        "contexts",
        "units",
        "continuations",
        "facts",
        "diagnostics",
        "coverage",
    }
)
_LOW_LEVEL_SOURCE_FIELDS = frozenset({"document_name", "content_sha256", "byte_length"})
_COVERAGE_FIELDS = frozenset(
    {
        "selected_member_byte_verified",
        "parser_coverage",
        "parser_context_count",
        "parser_unit_count",
        "parser_continuation_count",
        "parser_fact_count",
        "parser_diagnostic_count",
        "package_member_set_complete",
        "filing_complete",
        "taxonomy_validation_complete",
        "relationship_validation_complete",
        "calculation_validation_complete",
        "xbrl_semantic_attested",
        "company_facts_attested",
        "archive_object_presence_attested",
    }
)
_NONCLAIM_FIELDS = frozenset(
    {
        "package_member_set_complete",
        "filing_complete",
        "taxonomy_validation_complete",
        "relationship_validation_complete",
        "calculation_validation_complete",
        "xbrl_semantic_attested",
        "company_facts_attested",
        "archive_object_presence_attested",
        "wrapper_raw_ledger_written",
        "wrapper_network_accessed",
        "wrapper_storage_accessed",
    }
)


class IxbrlExtractionError(ValueError):
    """A parser result cannot make the extraction claim encoded by ``ffxbrl``."""


def _strict_object(value: Any, *, field: str, required: frozenset[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise IxbrlExtractionError(f"{field} must be an object")
    try:
        iterator = iter(value.items())
    except Exception as exc:  # noqa: BLE001 - hostile mapping boundary.
        raise IxbrlExtractionError(f"{field} cannot be iterated") from exc
    out: dict[str, Any] = {}
    for index in range(len(required) + 1):
        try:
            pair = next(iterator)
        except StopIteration:
            break
        except Exception as exc:  # noqa: BLE001 - hostile mapping boundary.
            raise IxbrlExtractionError(f"{field} iterator failed") from exc
        if index == len(required):
            raise IxbrlExtractionError(f"{field} shape is invalid")
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise IxbrlExtractionError(f"{field} iterator yielded an invalid entry")
        key, item = pair
        if not isinstance(key, str) or key not in required or key in out:
            raise IxbrlExtractionError(f"{field} shape is invalid")
        out[key] = item
    if len(out) != len(required):
        raise IxbrlExtractionError(f"{field} shape is invalid")
    return out


def _text(value: Any, *, field: str, maximum: int = MAX_TEXT_BYTES) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise IxbrlExtractionError(f"{field} must be non-empty normalized text")
    try:
        if len(value.encode("utf-8")) > maximum:
            raise IxbrlExtractionError(f"{field} exceeds bounded text length")
    except UnicodeError as exc:
        raise IxbrlExtractionError(f"{field} is not valid UTF-8 text") from exc
    return value


def _nullable_http_metadata(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or any(char in value for char in ("\x00", "\r", "\n")):
        raise IxbrlExtractionError(f"{field} contains invalid HTTP header characters")
    try:
        if len(value.encode("utf-8")) > MAX_METADATA_BYTES:
            raise IxbrlExtractionError(f"{field} exceeds bounded text length")
    except UnicodeError as exc:
        raise IxbrlExtractionError(f"{field} is not valid UTF-8 text") from exc
    return value


def _sha256(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise IxbrlExtractionError(f"{field} must be lowercase SHA-256 hex")
    return value


def _length(value: Any, *, field: str, maximum: int = HARD_MAX_MEMBER_BYTES) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > maximum:
        raise IxbrlExtractionError(f"{field} is outside the bounded byte range")
    return value


def _clock(value: Any, *, field: str) -> str:
    if not isinstance(value, (str, datetime)):
        raise IxbrlExtractionError(f"{field} must be a UTC timestamp")
    try:
        parsed = parse_utc(value, field=field)
    except ValueError as exc:
        raise IxbrlExtractionError(str(exc)) from exc
    if parsed is None:  # pragma: no cover - required above.
        raise IxbrlExtractionError(f"{field} is required")
    return utc_text(parsed) or ""  # pragma: no cover - parsed is non-null.


def _safe_member_name(value: Any, *, field: str) -> str:
    name = _text(value, field=field, maximum=MAX_METADATA_BYTES)
    parts = name.split("/")
    if (
        not _MEMBER_NAME_RE.fullmatch(name)
        or name.startswith("/")
        or "\\" in name
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise IxbrlExtractionError(f"{field} is not a safe archive member name")
    return name


def _storage_key(digest: str) -> str:
    return f"objects/sha256/{digest[:2]}/{digest}.bin.gz"


def _copy_json(
    value: Any,
    *,
    field: str,
    budget: list[int],
    string_budget: list[int] | None = None,
    depth: int = 0,
    allow_tuples: bool = False,
) -> Any:
    """Copy a parser output without trusting custom mappings or iterables."""
    if string_budget is None:
        string_budget = [HARD_MAX_JSON_DECODED_STRING_BYTES]
    if depth > HARD_MAX_JSON_DEPTH:
        raise IxbrlExtractionError(f"{field} exceeds JSON nesting safety limit")
    budget[0] -= 1
    if budget[0] < 0:
        raise IxbrlExtractionError(f"{field} exceeds JSON node safety limit")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value < -(1 << 63) or value > (1 << 63) - 1:
            raise IxbrlExtractionError(f"{field} integer is outside signed-64-bit range")
        return value
    if isinstance(value, float):
        raise IxbrlExtractionError(f"{field} cannot contain binary floats")
    if isinstance(value, str):
        try:
            encoded = value.encode("utf-8")
            if len(encoded) > MAX_TEXT_BYTES:
                raise IxbrlExtractionError(f"{field} string exceeds bounded text length")
        except UnicodeError as exc:
            raise IxbrlExtractionError(f"{field} string is not valid UTF-8 text") from exc
        string_budget[0] -= len(encoded)
        if string_budget[0] < 0:
            raise IxbrlExtractionError(f"{field} exceeds decoded-string safety limit")
        return value
    if isinstance(value, Mapping):
        try:
            iterator = iter(value.items())
        except Exception as exc:  # noqa: BLE001 - hostile mapping boundary.
            raise IxbrlExtractionError(f"{field} cannot be iterated") from exc
        out: dict[str, Any] = {}
        for index in range(HARD_MAX_JSON_NODES + 1):
            try:
                pair = next(iterator)
            except StopIteration:
                break
            except Exception as exc:  # noqa: BLE001 - hostile mapping boundary.
                raise IxbrlExtractionError(f"{field} iterator failed") from exc
            if index == HARD_MAX_JSON_NODES:
                raise IxbrlExtractionError(f"{field} has too many object entries")
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise IxbrlExtractionError(f"{field} iterator yielded an invalid entry")
            key, item = pair
            if not isinstance(key, str) or key in out:
                raise IxbrlExtractionError(f"{field} object keys are invalid")
            budget[0] -= 1
            if budget[0] < 0:
                raise IxbrlExtractionError(f"{field} exceeds JSON node safety limit")
            try:
                encoded_key = key.encode("utf-8")
                if len(encoded_key) > MAX_METADATA_BYTES:
                    raise IxbrlExtractionError(f"{field} object key exceeds bounded text length")
            except UnicodeError as exc:
                raise IxbrlExtractionError(f"{field} object key is not valid UTF-8 text") from exc
            string_budget[0] -= len(encoded_key)
            if string_budget[0] < 0:
                raise IxbrlExtractionError(f"{field} exceeds decoded-string safety limit")
            out[key] = _copy_json(
                item,
                field=field,
                budget=budget,
                string_budget=string_budget,
                depth=depth + 1,
                allow_tuples=allow_tuples,
            )
        return out
    if type(value) is list or (allow_tuples and type(value) is tuple):
        if len(value) > HARD_MAX_JSON_NODES:
            raise IxbrlExtractionError(f"{field} has too many array entries")
        return [
            _copy_json(
                item,
                field=field,
                budget=budget,
                string_budget=string_budget,
                depth=depth + 1,
                allow_tuples=allow_tuples,
            )
            for item in value
        ]
    raise IxbrlExtractionError(f"{field} must contain JSON-native values")


def _copy_parser_value(value: Any) -> tuple[dict[str, Any], bytes]:
    copied = _copy_json(value, field="parser output", budget=[HARD_MAX_JSON_NODES])
    if not isinstance(copied, dict):
        raise IxbrlExtractionError("parser output must be an object")
    encoded = canonical_json(copied).encode("utf-8")
    if len(encoded) > HARD_MAX_PARSER_OUTPUT_BYTES:
        raise IxbrlExtractionError("parser output exceeds byte safety limit")
    return copied, encoded


def _reject_reserved_keys(
    value: Any,
    *,
    field: str,
    allowed_at_root: frozenset[str] = frozenset(),
    _at_root: bool = True,
) -> None:
    """Keep the wrapper-owned ``ffxbrl_*`` namespace out of parser data."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key.startswith(FFXBRL_ID_PREFIX) and (not _at_root or key not in allowed_at_root):
                raise IxbrlExtractionError(f"{field} contains reserved wrapper field: {key}")
            _reject_reserved_keys(item, field=field, _at_root=False)
    elif type(value) is list:
        for item in value:
            _reject_reserved_keys(item, field=field, _at_root=False)


def _normalise_low_level_output(
    value: Any,
    *,
    document_name: str,
    digest: str,
    length: int,
    expected_schema: str | None = None,
    expected_profile: str | None = None,
    expected_version: str | None = None,
    expected_algorithm_fingerprint: str | None = None,
    expected_transform_registry: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Admit the strict parser's fixed wire contract without changing its data."""
    copied, _encoded = _copy_parser_value(value)
    _reject_reserved_keys(copied, field="parser output")
    output = _strict_object(copied, field="parser output", required=_LOW_LEVEL_OUTPUT_FIELDS)
    schema = _text(output["schema"], field="parser output.schema", maximum=MAX_METADATA_BYTES)
    if expected_schema is not None and schema != expected_schema:
        raise IxbrlExtractionError("parser output schema does not match parser contract")
    parser = _strict_object(output["parser"], field="parser output.parser", required=_PARSER_FIELDS)
    parser_value = _copy_json(parser, field="parser output.parser", budget=[HARD_MAX_JSON_NODES])
    assert isinstance(parser_value, dict)  # _strict_object and _copy_json guarantee this.
    parser_value["profile"] = _text(
        parser_value["profile"], field="parser output.parser.profile", maximum=MAX_METADATA_BYTES
    )
    parser_value["version"] = _text(
        parser_value["version"], field="parser output.parser.version", maximum=MAX_METADATA_BYTES
    )
    parser_value["algorithm_fingerprint"] = _sha256(
        parser_value["algorithm_fingerprint"], field="parser output.parser.algorithm_fingerprint"
    )
    for name in ("library", "library_version", "xml_library_version"):
        parser_value[name] = _text(
            parser_value[name], field=f"parser output.parser.{name}", maximum=MAX_METADATA_BYTES
        )
    parser_value["transform_registry"] = _normalise_transform_registry(
        parser_value["transform_registry"], field="parser output transform_registry"
    )
    if expected_profile is not None and parser_value["profile"] != expected_profile:
        raise IxbrlExtractionError("parser output profile does not match parser contract")
    if expected_version is not None and parser_value["version"] != expected_version:
        raise IxbrlExtractionError("parser output version does not match parser contract")
    if (
        expected_algorithm_fingerprint is not None
        and parser_value["algorithm_fingerprint"] != expected_algorithm_fingerprint
    ):
        raise IxbrlExtractionError("parser output algorithm fingerprint does not match parser contract")
    if (
        expected_transform_registry is not None
        and parser_value["transform_registry"] != expected_transform_registry
    ):
        raise IxbrlExtractionError("parser output transform registry does not match parser contract")
    source = _strict_object(output["source"], field="parser output.source", required=_LOW_LEVEL_SOURCE_FIELDS)
    if (
        _safe_member_name(source["document_name"], field="parser output.source.document_name")
        != document_name
        or _sha256(source["content_sha256"], field="parser output.source.content_sha256") != digest
        or _length(source["byte_length"], field="parser output.source.byte_length") != length
    ):
        raise IxbrlExtractionError("parser output source does not bind supplied member bytes")
    for field in ("contexts", "units", "continuations", "facts", "diagnostics"):
        if type(output[field]) is not list or len(output[field]) > FFXBRL_LIMITS[f"max_{field}"]:
            raise IxbrlExtractionError(f"parser output {field} must be a bounded array")
    if not isinstance(output["document"], dict) or not isinstance(output["coverage"], dict):
        raise IxbrlExtractionError("parser output document and coverage must be objects")
    if output["document"].get("kind") not in {"inline_xbrl", "xbrl_instance"}:
        raise IxbrlExtractionError("parser output document kind is not admissible for ixbrl extraction")
    # The parser's own source witness is checked above; the outer artifact keeps
    # the stronger package/receipt witness rather than duplicating a second copy.
    return {
        "schema": schema,
        "parser": parser_value,
        "document": output["document"],
        "contexts": output["contexts"],
        "units": output["units"],
        "continuations": output["continuations"],
        "facts": output["facts"],
        "diagnostics": output["diagnostics"],
        "coverage": output["coverage"],
    }


def _normalise_transform_registry(value: Any, *, field: str) -> list[dict[str, str]]:
    """Admit the parser's stable, qname-sorted primitive transform inventory."""
    if type(value) is not list or len(value) > MAX_METADATA_BYTES:
        raise IxbrlExtractionError(f"{field} must be a bounded array")
    registry: list[dict[str, str]] = []
    previous_qname: str | None = None
    for index, raw in enumerate(value):
        item = _strict_object(
            raw,
            field=f"{field}[{index}]",
            required=frozenset({"qname", "kind"}),
        )
        qname = _text(item["qname"], field=f"{field}[{index}].qname", maximum=MAX_METADATA_BYTES)
        kind = _text(item["kind"], field=f"{field}[{index}].kind", maximum=MAX_METADATA_BYTES)
        if previous_qname is not None and qname <= previous_qname:
            raise IxbrlExtractionError(f"{field} must be strictly sorted by qname")
        previous_qname = qname
        registry.append({"qname": qname, "kind": kind})
    return registry


def _normalise_receipt(value: Any, *, document_id: str, archive_url: str, digest: str, length: int) -> dict[str, Any]:
    receipt = _strict_object(value, field="source member retrieval", required=_RECEIPT_FIELDS)
    if receipt["schema"] != ARCHIVE_RECEIPT_SCHEMA or receipt["status"] != "retrieved":
        raise IxbrlExtractionError("source member retrieval is not a retrieved SEC archive receipt")
    if receipt["document_id"] != document_id or receipt["archive_url"] != archive_url:
        raise IxbrlExtractionError("source member retrieval does not bind expected document")
    if (
        _sha256(receipt["content_sha256"], field="source member retrieval.content_sha256") != digest
        or _length(receipt["byte_length"], field="source member retrieval.byte_length") != length
        or receipt["storage_key"] != _storage_key(digest)
    ):
        raise IxbrlExtractionError("source member retrieval does not bind stored bytes")
    retrieved_at = _clock(receipt["retrieved_at"], field="source member retrieval.retrieved_at")
    if receipt["retrieved_at"] != retrieved_at:
        raise IxbrlExtractionError("source member retrieval.retrieved_at is not canonical UTC")
    body = {
        "schema": ARCHIVE_RECEIPT_SCHEMA,
        "status": "retrieved",
        "document_id": document_id,
        "archive_url": archive_url,
        "retrieved_at": retrieved_at,
        "content_sha256": digest,
        "byte_length": length,
        "storage_key": _storage_key(digest),
        "http_etag": _nullable_http_metadata(receipt["http_etag"], field="source member retrieval.http_etag"),
        "http_last_modified": _nullable_http_metadata(
            receipt["http_last_modified"], field="source member retrieval.http_last_modified"
        ),
    }
    receipt_id = receipt["receipt_id"]
    expected_id = stable_id("sec_archive_receipt", body)
    if not isinstance(receipt_id, str) or not _RECEIPT_ID_RE.fullmatch(receipt_id) or not hmac.compare_digest(receipt_id, expected_id):
        raise IxbrlExtractionError("source member retrieval identity mismatch")
    return {"receipt_id": receipt_id, **body}


def _normalise_source(value: Any) -> dict[str, Any]:
    source = _strict_object(value, field="extraction source", required=_SOURCE_FIELDS)
    if source["package_schema"] != FILING_PACKAGE_SCHEMA:
        raise IxbrlExtractionError("source package schema is invalid")
    package_id = source["package_id"]
    if not isinstance(package_id, str) or not _PACKAGE_ID_RE.fullmatch(package_id):
        raise IxbrlExtractionError("source package_id is invalid")
    filing = _strict_object(source["filing"], field="extraction filing", required=_FILING_FIELDS)
    if filing["manifest_schema"] != "fundamental_forensics.sec_filing_manifest/v1":
        raise IxbrlExtractionError("source filing manifest schema is invalid")
    try:
        cik = canonical_cik(filing["cik"])
    except Exception as exc:  # noqa: BLE001 - source boundary.
        raise IxbrlExtractionError("source filing CIK is invalid") from exc
    accession = _text(filing["accession"], field="source filing accession", maximum=MAX_METADATA_BYTES)
    filing_id = stable_id("sec_filing", cik, accession)
    expected_index_url = archive_index_url(cik, accession)
    if (
        filing["filing_id"] != filing_id
        or not isinstance(filing["manifest_id"], str)
        or not re.fullmatch(r"ffsec_manifest_[a-f0-9]{64}", filing["manifest_id"])
        or filing["archive_index_url"] != expected_index_url
    ):
        raise IxbrlExtractionError("source filing binding is invalid")
    member = _strict_object(source["member"], field="source member", required=_MEMBER_FIELDS)
    name = _safe_member_name(member["document_name"], field="source member document_name")
    role = member["role"]
    if role not in {"primary", "archive", "exhibit"}:
        raise IxbrlExtractionError("source member role is invalid")
    document_id = stable_id("sec_document", cik, accession, role, name)
    archive_url = archive_document_url(cik, accession, name)
    digest = _sha256(member["content_sha256"], field="source member content_sha256")
    length = _length(member["byte_length"], field="source member byte_length")
    if (
        member["document_id"] != document_id
        or member["archive_url"] != archive_url
        or member["storage_key"] != _storage_key(digest)
    ):
        raise IxbrlExtractionError("source member binding is invalid")
    receipt = _normalise_receipt(
        member["retrieval"],
        document_id=document_id,
        archive_url=archive_url,
        digest=digest,
        length=length,
    )
    return {
        "package_schema": FILING_PACKAGE_SCHEMA,
        "package_id": package_id,
        "filing": {
            "manifest_schema": filing["manifest_schema"],
            "cik": cik,
            "accession": accession,
            "filing_id": filing_id,
            "manifest_id": filing["manifest_id"],
            "archive_index_url": expected_index_url,
        },
        "member": {
            "document_name": name,
            "document_id": document_id,
            "role": role,
            "archive_url": archive_url,
            "content_sha256": digest,
            "byte_length": length,
            "storage_key": _storage_key(digest),
            "retrieval": receipt,
        },
    }


def _parser_api() -> tuple[Any, Any, str, str, str, str, list[dict[str, str]]]:
    """Lazy-import the parser so this wrapper never imports network collectors."""
    try:
        module = importlib.import_module("collectors.sec_filing_parser")
        parser = getattr(module, "parse_sec_filing_document")
        parse_error = getattr(module, "SecFilingParseError")
        schema = getattr(module, "SEC_FILING_PARSER_SCHEMA")
        profile = getattr(module, "SEC_FILING_PARSER_PROFILE")
        version = getattr(module, "SEC_FILING_PARSER_VERSION")
        algorithm_fingerprint = getattr(module, "SEC_FILING_PARSER_ALGORITHM_FINGERPRINT")
        transforms = getattr(module, "SUPPORTED_TRANSFORMS")
        parser_limits = getattr(module, "PARSER_LIMITS")
    except (ImportError, AttributeError) as exc:
        raise IxbrlExtractionError("strict SEC filing parser is unavailable") from exc
    if not callable(parser) or not isinstance(parse_error, type) or not issubclass(parse_error, Exception):
        raise IxbrlExtractionError("strict SEC filing parser contract is invalid")
    if not isinstance(transforms, Mapping):
        raise IxbrlExtractionError("strict SEC filing parser transform registry contract is invalid")
    expected_registry = _normalise_transform_registry(
        [
            {"qname": qname, "kind": kind}
            for qname, kind in sorted(transforms.items())
        ],
        field="installed parser transform registry",
    )
    if not isinstance(parser_limits, Mapping):
        raise IxbrlExtractionError("strict SEC filing parser limits contract is invalid")
    for field, maximum in _PARSER_ENVELOPE_FIELDS.items():
        configured = parser_limits.get(field)
        if isinstance(configured, bool) or not isinstance(configured, int) or configured < 1:
            raise IxbrlExtractionError("strict SEC filing parser limits contract is invalid")
        if configured > maximum:
            raise IxbrlExtractionError(
                "strict SEC filing parser admission envelope exceeds ixbrl wrapper envelope"
            )
    return (
        parser,
        parse_error,
        _text(schema, field="parser schema", maximum=MAX_METADATA_BYTES),
        _text(profile, field="parser profile", maximum=MAX_METADATA_BYTES),
        _text(version, field="parser version", maximum=MAX_METADATA_BYTES),
        _sha256(algorithm_fingerprint, field="parser algorithm fingerprint"),
        expected_registry,
    )


def _parser_counts(output: Mapping[str, Any]) -> tuple[int, int, int, int, int]:
    """Derive only bounded summary counts; parser semantics stay in its payload."""
    names = ("contexts", "units", "continuations", "facts", "diagnostics")
    counts: list[int] = []
    for name in names:
        value = output.get(name, [])
        if type(value) is not list or len(value) > FFXBRL_LIMITS[f"max_{name}"]:
            raise IxbrlExtractionError(f"parser output {name} must be a bounded array")
        counts.append(len(value))
    return tuple(counts)  # type: ignore[return-value]


_OUTER_ID_FIELD = {
    "contexts": "ffxbrl_context_id",
    "units": "ffxbrl_unit_id",
    "continuations": "ffxbrl_continuation_id",
    "facts": "ffxbrl_fact_id",
}
_PARSER_LOCAL_ID_FIELD = {
    "contexts": "context_id",
    "units": "unit_id",
    "continuations": "continuation_id",
    "facts": "fact_id",
}
_SOURCE_SPAN_FIELDS = frozenset({"start", "end"})
_CONTINUATION_OUTER_REF_FIELD = "ffxbrl_continued_at_ref_id"
_FACT_CONTINUATION_OUTER_REF_FIELD = "ffxbrl_continuation_ref_ids"


def _child_source_span(item: Mapping[str, Any], *, field: str, source_length: int) -> dict[str, int]:
    """Require the parser's exact original-byte provenance for every child."""
    if "source_spans" in item:
        raise IxbrlExtractionError(f"{field} cannot use source_spans")
    span = _strict_object(item.get("source_span"), field=f"{field}.source_span", required=_SOURCE_SPAN_FIELDS)
    start = span["start"]
    end = span["end"]
    if (
        isinstance(start, bool)
        or not isinstance(start, int)
        or isinstance(end, bool)
        or not isinstance(end, int)
        or start < 0
        or end <= start
        or end > source_length
    ):
        raise IxbrlExtractionError(f"{field}.source_span is outside the selected member bytes")
    return {"start": start, "end": end}


def _child_order_key(item: Mapping[str, Any], span: Mapping[str, int]) -> tuple[int, int, str]:
    """Source byte order, with a content-stable tie break for equal starts."""
    raw_item = {key: value for key, value in item.items() if not key.startswith(FFXBRL_ID_PREFIX)}
    return int(span["start"]), int(span["end"]), canonical_json(raw_item)


def _outerise_parser_arrays(
    arrays: Mapping[str, list[Any]],
    source: Mapping[str, Any],
    *,
    final: bool,
) -> dict[str, list[Any]]:
    """Attach package-scoped immutable IDs while retaining parser-local IDs."""
    package_id = str(source["package_id"])
    document_id = str(source["member"]["document_id"])
    digest = str(source["member"]["content_sha256"])
    source_length = int(source["member"]["byte_length"])
    out = {name: list(arrays[name]) for name in arrays}
    for source_order, raw in enumerate(out["diagnostics"]):
        _reject_reserved_keys(raw, field=f"parser diagnostics[{source_order}]")
    local_maps: dict[str, dict[str, str]] = {}
    for kind in ("contexts", "units", "continuations", "facts"):
        item_id_field = _PARSER_LOCAL_ID_FIELD[kind]
        outer_id_field = _OUTER_ID_FIELD[kind]
        canonical_items: list[Any] = []
        local_map: dict[str, str] = {}
        previous_order_key: tuple[int, int, str] | None = None
        for source_order, raw in enumerate(out[kind]):
            if not isinstance(raw, Mapping):
                raise IxbrlExtractionError(f"parser {kind}[{source_order}] must be an object")
            allowed = {"ffxbrl_span_id", outer_id_field} if final else set()
            if final:
                if kind == "continuations":
                    allowed.add(_CONTINUATION_OUTER_REF_FIELD)
                elif kind == "facts":
                    allowed.update(
                        {
                            "ffxbrl_context_id",
                            "ffxbrl_unit_id",
                            _FACT_CONTINUATION_OUTER_REF_FIELD,
                        }
                    )
            _reject_reserved_keys(
                raw,
                field=f"parser {kind}[{source_order}]",
                allowed_at_root=frozenset(allowed),
            )
            item = dict(raw)
            supplied_outer = item.pop(outer_id_field, None)
            supplied_span = item.pop("ffxbrl_span_id", None)
            field = f"parser {kind}[{source_order}]"
            span = _child_source_span(item, field=field, source_length=source_length)
            order_key = _child_order_key(item, span)
            if previous_order_key is not None and order_key <= previous_order_key:
                raise IxbrlExtractionError(f"parser {kind} is not in canonical source-span order")
            previous_order_key = order_key
            span_id = stable_id(
                "ffxbrl_span", package_id, document_id, digest, kind, span
            )
            if kind == "facts":
                local_id = item.get(item_id_field)
                if local_id is not None:
                    _text(local_id, field=f"{field}.{item_id_field}", maximum=MAX_METADATA_BYTES)
                outer_id = stable_id(
                    "ffxbrl_fact", package_id, document_id, digest, kind, source_order, span_id
                )
            else:
                local_id = _text(
                    item.get(item_id_field), field=f"{field}.{item_id_field}", maximum=MAX_METADATA_BYTES
                )
                outer_id = stable_id(
                    f"ffxbrl_{kind[:-1]}",
                    package_id,
                    document_id,
                    digest,
                    local_id,
                    source_order,
                    span_id,
                )
            if final and (supplied_span != span_id or supplied_outer != outer_id):
                raise IxbrlExtractionError(f"parser {kind}[{source_order}] outer identity mismatch")
            if kind != "facts" and local_id in local_map:
                raise IxbrlExtractionError(f"parser {kind} contains duplicate local identity: {local_id}")
            if kind != "facts":
                local_map[local_id] = outer_id
            item["ffxbrl_span_id"] = span_id
            item[outer_id_field] = outer_id
            canonical_items.append(item)
        out[kind] = canonical_items
        local_maps[kind] = local_map

    continuation_map = local_maps["continuations"]
    for source_order, item in enumerate(out["continuations"]):
        assert isinstance(item, dict)  # constructed above.
        if "continued_at" not in item:
            raise IxbrlExtractionError(f"parser continuations[{source_order}].continued_at is required")
        target = item["continued_at"]
        if target is None:
            expected: str | None = None
        else:
            local_target = _text(
                target,
                field=f"parser continuations[{source_order}].continued_at",
                maximum=MAX_METADATA_BYTES,
            )
            if local_target not in continuation_map:
                raise IxbrlExtractionError(
                    f"parser continuations[{source_order}].continued_at references an unknown continuation"
                )
            expected = continuation_map[local_target]
        existing = item.get(_CONTINUATION_OUTER_REF_FIELD)
        if final and (
            _CONTINUATION_OUTER_REF_FIELD not in item or existing != expected
        ):
            raise IxbrlExtractionError(
                f"continuation outer reference {_CONTINUATION_OUTER_REF_FIELD} does not bind continued_at"
            )
        item[_CONTINUATION_OUTER_REF_FIELD] = expected

    # Preserve local cross-references but make their package-scoped targets
    # explicit for a later attestation/ledger join.  The low-level validator
    # remains responsible for XBRL relationship semantics.
    for item in out["facts"]:
        assert isinstance(item, dict)  # constructed above.
        for parser_keys, outer_key, target_kind in (
            (("context_ref", "context_id"), "ffxbrl_context_id", "contexts"),
            (("unit_ref", "unit_id"), "ffxbrl_unit_id", "units"),
        ):
            targets = [
                local_maps[target_kind][item[parser_key]]
                for parser_key in parser_keys
                if isinstance(item.get(parser_key), str) and item[parser_key] in local_maps[target_kind]
            ]
            if not targets:
                if outer_key in item:
                    raise IxbrlExtractionError(
                        f"fact outer reference {outer_key} has no matching parser local ID"
                    )
                continue
            expected = targets[0]
            if any(target != expected for target in targets[1:]):
                raise IxbrlExtractionError(f"fact outer reference {outer_key} has conflicting parser local IDs")
            existing = item.get(outer_key)
            if final and existing != expected:
                raise IxbrlExtractionError(f"fact outer reference {outer_key} does not bind parser local ID")
            item[outer_key] = expected
    for source_order, item in enumerate(out["facts"]):
        assert isinstance(item, dict)  # constructed above.
        if "continuation_chain" not in item:
            raise IxbrlExtractionError(f"parser facts[{source_order}].continuation_chain is required")
        chain = item["continuation_chain"]
        if type(chain) is not list or len(chain) > FFXBRL_LIMITS["max_continuation_chain"]:
            raise IxbrlExtractionError(f"parser facts[{source_order}].continuation_chain must be a bounded array")
        resolved_chain: list[str] = []
        seen_chain: set[str] = set()
        for chain_index, raw_target in enumerate(chain):
            local_target = _text(
                raw_target,
                field=f"parser facts[{source_order}].continuation_chain[{chain_index}]",
                maximum=MAX_METADATA_BYTES,
            )
            if local_target not in continuation_map:
                raise IxbrlExtractionError(
                    f"parser facts[{source_order}].continuation_chain references an unknown continuation"
                )
            if local_target in seen_chain:
                raise IxbrlExtractionError(
                    f"parser facts[{source_order}].continuation_chain contains a duplicate continuation"
                )
            seen_chain.add(local_target)
            resolved_chain.append(continuation_map[local_target])
        existing_chain = item.get(_FACT_CONTINUATION_OUTER_REF_FIELD)
        if final and (
            _FACT_CONTINUATION_OUTER_REF_FIELD not in item or existing_chain != resolved_chain
        ):
            raise IxbrlExtractionError(
                f"fact outer reference {_FACT_CONTINUATION_OUTER_REF_FIELD} does not bind continuation_chain"
            )
        item[_FACT_CONTINUATION_OUTER_REF_FIELD] = resolved_chain
    return out


def _low_level_reconstruction(
    *,
    parser_schema: str,
    parser: Mapping[str, Any],
    source: Mapping[str, Any],
    document: Mapping[str, Any],
    arrays: Mapping[str, list[Any]],
    coverage: Mapping[str, Any],
) -> dict[str, Any]:
    """Remove outer receipt IDs before handing a result back to the parser validator."""
    raw_arrays: dict[str, list[Any]] = {}
    outer_fields = {
        "ffxbrl_span_id",
        *set(_OUTER_ID_FIELD.values()),
        _CONTINUATION_OUTER_REF_FIELD,
        _FACT_CONTINUATION_OUTER_REF_FIELD,
    }
    outer_fact_refs = {"ffxbrl_context_id", "ffxbrl_unit_id"}
    for name, values in arrays.items():
        rebuilt: list[Any] = []
        for value in values:
            if not isinstance(value, Mapping):
                raise IxbrlExtractionError(f"ixbrl {name} must contain objects")
            item = {str(key): item for key, item in value.items() if key not in outer_fields}
            if name == "facts":
                item = {key: item for key, item in item.items() if key not in outer_fact_refs}
            rebuilt.append(item)
        raw_arrays[name] = rebuilt
    member = source["member"]
    return {
        "schema": parser_schema,
        "parser": dict(parser),
        "source": {
            "document_name": member["document_name"],
            "content_sha256": member["content_sha256"],
            "byte_length": member["byte_length"],
        },
        "document": dict(document),
        "contexts": raw_arrays["contexts"],
        "units": raw_arrays["units"],
        "continuations": raw_arrays["continuations"],
        "facts": raw_arrays["facts"],
        "diagnostics": raw_arrays["diagnostics"],
        "coverage": dict(coverage),
    }


def _validate_low_level_reconstruction(
    value: Mapping[str, Any], *, source_content: bytes | None = None
) -> None:
    """Delegate the embedded parser claim to its authoritative strict validator."""
    try:
        module = importlib.import_module("collectors.sec_filing_parser")
    except ImportError as exc:
        raise IxbrlExtractionError("strict SEC filing parser validator is unavailable") from exc
    validator = getattr(module, "validate_sec_filing_parse_result", None)
    if not callable(validator):
        raise IxbrlExtractionError("strict SEC filing parser validator contract is invalid")
    try:
        if source_content is None:
            validator(value)
        else:
            validator(value, source_content=source_content)
    except Exception as exc:  # noqa: BLE001 - parser validation boundary.
        raise IxbrlExtractionError("embedded strict parser result is invalid") from exc


def _package_and_member(
    package: FilingPackage | Mapping[str, Any], document_name: str, content: bytes
) -> tuple[FilingPackage, dict[str, Any]]:
    verified_package = _rehydrate_filing_package_input(package)
    name = _safe_member_name(document_name, field="document_name")
    if not isinstance(content, bytes):
        raise IxbrlExtractionError("retained_member_bytes must be bytes")
    member = next(
        (item for item in verified_package.manifest["inventory"] if item["document_name"] == name),
        None,
    )
    if member is None:
        raise IxbrlExtractionError("document_name is not present in filing package inventory")
    if member["state"] != "stored":
        raise IxbrlExtractionError("document_name is not a stored filing package member")
    expected_length = int(member["byte_length"])
    expected_digest = str(member["content_sha256"])
    if len(content) != expected_length or not hmac.compare_digest(sha256(content).hexdigest(), expected_digest):
        raise IxbrlExtractionError("retained member bytes do not match filing package receipt")
    return verified_package, {str(key): value for key, value in member.items()}


def _rehydrate_filing_package_input(value: FilingPackage | Mapping[str, Any]) -> FilingPackage:
    """Revalidate caller evidence without dispatching to a nominal instance.

    A frozen dataclass is not an authority boundary: ``object.__new__`` can
    manufacture one with an arbitrary ``_record`` and subclasses can replace
    ``to_dict`` with unbounded or throwing code.  The only admissible nominal
    input is the exact base class, whose raw record is read through
    ``object.__getattribute__`` and immediately passed to FilingPackage's
    bounded canonical normalizer.
    """
    if type(value) is FilingPackage:
        try:
            raw_record = object.__getattribute__(value, "_record")
            # Base-class instances retain frozen MappingProxyType/tuple trees.
            # Materialize that tree with this module's bounded copier before
            # FilingPackage's independent canonical validator receives it.
            raw_record = _copy_json(
                raw_record,
                field="filing package nominal record",
                budget=[HARD_MAX_JSON_NODES],
                allow_tuples=True,
            )
        except IxbrlExtractionError as exc:
            raise IxbrlExtractionError(f"invalid filing package nominal record: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - hostile forged nominal input.
            raise IxbrlExtractionError("invalid filing package nominal record") from exc
    elif isinstance(value, FilingPackage):
        raise IxbrlExtractionError("invalid filing package subclass")
    else:
        raw_record = value
    try:
        return FilingPackage.from_dict(raw_record)
    except FilingPackageError as exc:
        raise IxbrlExtractionError(f"invalid filing package: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - no raw hostile mapping failures at the boundary.
        raise IxbrlExtractionError("invalid filing package") from exc


def _record_id(record: Mapping[str, Any]) -> str:
    body = dict(record)
    body.pop("extraction_id", None)
    return FFXBRL_ID_PREFIX + sha256(canonical_json(body).encode("utf-8")).hexdigest()


def ixbrl_extraction_id_for(record: Mapping[str, Any]) -> str:
    """Return the content ID committing every result field except its own ID."""
    return _record_id(record)


def _normalise_record(value: Any) -> dict[str, Any]:
    # Count the complete untrusted record once before projecting subfields.  A
    # fresh budget per array/coverage object would let an aggregate record
    # exceed the safety cap while every local component looked bounded.
    copied_record = _copy_json(value, field="ixbrl extraction", budget=[HARD_MAX_JSON_NODES])
    record = _strict_object(copied_record, field="ixbrl extraction", required=_TOP_FIELDS)
    if record["schema"] != FFXBRL_SCHEMA:
        raise IxbrlExtractionError("unsupported ixbrl extraction schema")
    source = _normalise_source(record["source"])
    parser = _strict_object(record["parser"], field="ixbrl parser", required=_PARSER_FIELDS)
    canonical_parser = _copy_json(parser, field="ixbrl parser", budget=[HARD_MAX_JSON_NODES])
    assert isinstance(canonical_parser, dict)  # _strict_object and _copy_json guarantee this.
    canonical_parser["profile"] = _text(
        canonical_parser["profile"], field="parser.profile", maximum=MAX_METADATA_BYTES
    )
    canonical_parser["version"] = _text(
        canonical_parser["version"], field="parser.version", maximum=MAX_METADATA_BYTES
    )
    canonical_parser["algorithm_fingerprint"] = _sha256(
        canonical_parser["algorithm_fingerprint"], field="parser.algorithm_fingerprint"
    )
    for name in ("library", "library_version", "xml_library_version"):
        canonical_parser[name] = _text(
            canonical_parser[name], field=f"parser.{name}", maximum=MAX_METADATA_BYTES
        )
    canonical_parser["transform_registry"] = _normalise_transform_registry(
        canonical_parser["transform_registry"], field="parser transform_registry"
    )
    extraction = _strict_object(record["extraction"], field="ixbrl extraction metadata", required=_EXTRACTION_FIELDS)
    computed_at = _clock(extraction["computed_at"], field="ixbrl extraction computed_at")
    if extraction["computed_at"] != computed_at:
        raise IxbrlExtractionError("ixbrl extraction computed_at is not canonical UTC")
    parser_schema = _text(
        extraction["parser_schema"], field="ixbrl extraction parser_schema", maximum=MAX_METADATA_BYTES
    )
    (
        _unused_parser,
        _unused_error,
        expected_schema,
        expected_profile,
        expected_version,
        expected_algorithm_fingerprint,
        expected_transform_registry,
    ) = _parser_api()
    if (
        parser_schema != expected_schema
        or canonical_parser["profile"] != expected_profile
        or canonical_parser["version"] != expected_version
        or canonical_parser["algorithm_fingerprint"] != expected_algorithm_fingerprint
        or canonical_parser["transform_registry"] != expected_transform_registry
    ):
        raise IxbrlExtractionError("ixbrl extraction parser contract does not match installed strict parser")
    document = _copy_json(record["document"], field="ixbrl document", budget=[HARD_MAX_JSON_NODES])
    if not isinstance(document, dict):
        raise IxbrlExtractionError("ixbrl document must be an object")
    _reject_reserved_keys(document, field="ixbrl document")
    if document.get("kind") not in {"inline_xbrl", "xbrl_instance"}:
        raise IxbrlExtractionError("ixbrl document kind is not admissible for ixbrl extraction")
    parsed_arrays: dict[str, list[Any]] = {}
    for name in ("contexts", "units", "continuations", "facts", "diagnostics"):
        copied = _copy_json(record[name], field=f"ixbrl {name}", budget=[HARD_MAX_JSON_NODES])
        if type(copied) is not list or len(copied) > FFXBRL_LIMITS[f"max_{name}"]:
            raise IxbrlExtractionError(f"ixbrl {name} must be a bounded array")
        parsed_arrays[name] = copied
    outer_arrays = _outerise_parser_arrays(parsed_arrays, source, final=True)
    if parsed_arrays != outer_arrays:
        raise IxbrlExtractionError("ixbrl parser arrays are not in canonical outer-identity form")
    receipt_at = parse_utc(source["member"]["retrieval"]["retrieved_at"], field="source member retrieved_at")
    computed_clock = parse_utc(computed_at, field="ixbrl extraction computed_at")
    if receipt_at is None or computed_clock is None:  # pragma: no cover - verified above.
        raise IxbrlExtractionError("source/member clocks are required")
    if computed_clock < receipt_at:
        raise IxbrlExtractionError("ixbrl extraction cannot predate source receipt")
    context_count, unit_count, continuation_count, fact_count, diagnostic_count = _parser_counts(outer_arrays)
    coverage = _strict_object(record["coverage"], field="ixbrl extraction coverage", required=_COVERAGE_FIELDS)
    parser_coverage = _copy_json(
        coverage["parser_coverage"], field="ixbrl parser coverage", budget=[HARD_MAX_JSON_NODES]
    )
    if not isinstance(parser_coverage, dict):
        raise IxbrlExtractionError("ixbrl parser coverage must be an object")
    _reject_reserved_keys(parser_coverage, field="ixbrl parser coverage")
    _validate_low_level_reconstruction(
        _low_level_reconstruction(
            parser_schema=parser_schema,
            parser=canonical_parser,
            source=source,
            document=document,
            arrays=outer_arrays,
            coverage=parser_coverage,
        )
    )
    expected_coverage = {
        "selected_member_byte_verified": True,
        "parser_coverage": parser_coverage,
        "parser_context_count": context_count,
        "parser_unit_count": unit_count,
        "parser_continuation_count": continuation_count,
        "parser_fact_count": fact_count,
        "parser_diagnostic_count": diagnostic_count,
        "package_member_set_complete": False,
        "filing_complete": False,
        "taxonomy_validation_complete": False,
        "relationship_validation_complete": False,
        "calculation_validation_complete": False,
        "xbrl_semantic_attested": False,
        "company_facts_attested": False,
        "archive_object_presence_attested": False,
    }
    if coverage != expected_coverage:
        raise IxbrlExtractionError("ixbrl extraction coverage does not match parser output")
    nonclaims = _strict_object(record["nonclaims"], field="ixbrl extraction nonclaims", required=_NONCLAIM_FIELDS)
    expected_nonclaims = {
        "package_member_set_complete": False,
        "filing_complete": False,
        "taxonomy_validation_complete": False,
        "relationship_validation_complete": False,
        "calculation_validation_complete": False,
        "xbrl_semantic_attested": False,
        "company_facts_attested": False,
        "archive_object_presence_attested": False,
        "wrapper_raw_ledger_written": False,
        "wrapper_network_accessed": False,
        "wrapper_storage_accessed": False,
    }
    if nonclaims != expected_nonclaims:
        raise IxbrlExtractionError("ixbrl extraction nonclaims are invalid")
    result = {
        "schema": FFXBRL_SCHEMA,
        "extraction_id": record["extraction_id"],
        "source": source,
        "parser": canonical_parser,
        "extraction": {
            "computed_at": computed_at,
            "parser_schema": parser_schema,
        },
        "document": document,
        "contexts": outer_arrays["contexts"],
        "units": outer_arrays["units"],
        "continuations": outer_arrays["continuations"],
        "facts": outer_arrays["facts"],
        "diagnostics": outer_arrays["diagnostics"],
        "coverage": expected_coverage,
        "nonclaims": expected_nonclaims,
    }
    expected_id = _record_id(result)
    actual_id = result["extraction_id"]
    if not isinstance(actual_id, str) or not _RESULT_ID_RE.fullmatch(actual_id) or not hmac.compare_digest(actual_id, expected_id):
        raise IxbrlExtractionError("ixbrl extraction identity mismatch")
    encoded = canonical_json(result).encode("utf-8")
    if len(encoded) > HARD_MAX_FFXBRL_BYTES:
        raise IxbrlExtractionError("ixbrl extraction exceeds byte safety limit")
    return result


def validate_ixbrl_extraction(value: Mapping[str, Any]) -> None:
    """Validate every immutable result boundary without accessing its source bytes."""
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
class IxbrlExtraction:
    """Read-only view of a canonical parser result bound to a package member."""

    _record: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "_record", _freeze(_normalise_record(self._record)))

    @property
    def extraction_id(self) -> str:
        return str(self._record["extraction_id"])

    @property
    def content_id(self) -> str:
        return self.extraction_id

    @property
    def manifest(self) -> Mapping[str, Any]:
        return self._record

    def to_dict(self) -> dict[str, Any]:
        return _thaw(self._record)

    def to_json_bytes(self) -> bytes:
        return canonical_json(self.to_dict()).encode("utf-8")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "IxbrlExtraction":
        return cls(value)

    @classmethod
    def from_json_bytes(cls, content: bytes) -> "IxbrlExtraction":
        return ixbrl_extraction_from_json_bytes(content)


def _rehydrate_ixbrl_extraction_input(
    value: IxbrlExtraction | Mapping[str, Any],
) -> IxbrlExtraction:
    """Revalidate a public extraction input before any nominal method runs.

    See ``_rehydrate_filing_package_input``.  This keeps both replay and JSON
    serialization bounded even when a caller fabricates an ``IxbrlExtraction``
    instance or supplies a subclass with hostile serialization methods.
    """
    if type(value) is IxbrlExtraction:
        try:
            raw_record = object.__getattribute__(value, "_record")
            # The exact base class stores canonical arrays as tuples.  Do not
            # call its ``to_dict`` method: a forged nominal can replace the
            # backing tree even though it has the right runtime type.
            raw_record = _copy_json(
                raw_record,
                field="ixbrl extraction nominal record",
                budget=[HARD_MAX_JSON_NODES],
                allow_tuples=True,
            )
        except IxbrlExtractionError as exc:
            raise IxbrlExtractionError(f"invalid ixbrl extraction nominal record: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - hostile forged nominal input.
            raise IxbrlExtractionError("invalid ixbrl extraction nominal record") from exc
    elif isinstance(value, IxbrlExtraction):
        raise IxbrlExtractionError("invalid ixbrl extraction subclass")
    else:
        raw_record = value
    try:
        return IxbrlExtraction.from_dict(raw_record)
    except IxbrlExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001 - no raw hostile mapping failures at the boundary.
        raise IxbrlExtractionError("invalid ixbrl extraction") from exc


def build_ixbrl_extraction(
    package: FilingPackage | Mapping[str, Any],
    document_name: str,
    retained_member_bytes: bytes,
    *,
    computed_at: str | datetime,
) -> IxbrlExtraction:
    """Parse one receipt-bound stored member and seal the resulting offline artifact."""
    verified_package, member = _package_and_member(package, document_name, retained_member_bytes)
    computed = _clock(computed_at, field="computed_at")
    package_assembled_at = _clock(
        verified_package.manifest["assembly"]["assembled_at"],
        field="filing package assembly.assembled_at",
    )
    computed_clock = parse_utc(computed, field="computed_at")
    assembled_clock = parse_utc(package_assembled_at, field="filing package assembly.assembled_at")
    if computed_clock is None or assembled_clock is None:  # pragma: no cover - both are required above.
        raise IxbrlExtractionError("computed_at and filing package assembly clock are required")
    if computed_clock < assembled_clock:
        raise IxbrlExtractionError("ixbrl extraction cannot predate filing package assembly")
    (
        parser,
        parse_error,
        parser_schema,
        parser_profile,
        parser_version,
        parser_algorithm_fingerprint,
        parser_transform_registry,
    ) = _parser_api()
    try:
        parser_result = parser(retained_member_bytes, document_name=document_name)
    except parse_error as exc:
        raise IxbrlExtractionError(f"strict SEC filing parser rejected member: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - parser boundary must never leak partial state.
        raise IxbrlExtractionError("strict SEC filing parser failed") from exc
    parser_output = _normalise_low_level_output(
        parser_result,
        document_name=document_name,
        digest=str(member["content_sha256"]),
        length=int(member["byte_length"]),
        expected_schema=parser_schema,
        expected_profile=parser_profile,
        expected_version=parser_version,
        expected_algorithm_fingerprint=parser_algorithm_fingerprint,
        expected_transform_registry=parser_transform_registry,
    )
    source = {
        "package_schema": FILING_PACKAGE_SCHEMA,
        "package_id": verified_package.package_id,
        "filing": verified_package.to_dict()["filing"],
        "member": {
            "document_name": member["document_name"],
            "document_id": member["document_id"],
            "role": member["role"],
            "archive_url": member["archive_url"],
            "content_sha256": member["content_sha256"],
            "byte_length": member["byte_length"],
            "storage_key": member["storage_key"],
            "retrieval": member["retrieval"],
        },
    }
    _validate_low_level_reconstruction(
        _low_level_reconstruction(
            parser_schema=parser_output["schema"],
            parser=parser_output["parser"],
            source=source,
            document=parser_output["document"],
            arrays={
                name: parser_output[name]
                for name in ("contexts", "units", "continuations", "facts", "diagnostics")
            },
            coverage=parser_output["coverage"],
        ),
        source_content=retained_member_bytes,
    )
    parser_arrays = _outerise_parser_arrays(
        {
            name: parser_output[name]
            for name in ("contexts", "units", "continuations", "facts", "diagnostics")
        },
        source,
        final=False,
    )
    context_count, unit_count, continuation_count, fact_count, diagnostic_count = _parser_counts(parser_arrays)
    record: dict[str, Any] = {
        "schema": FFXBRL_SCHEMA,
        "extraction_id": "",
        "source": source,
        "parser": parser_output["parser"],
        "extraction": {
            "computed_at": computed,
            "parser_schema": parser_schema,
        },
        "document": parser_output["document"],
        "contexts": parser_arrays["contexts"],
        "units": parser_arrays["units"],
        "continuations": parser_arrays["continuations"],
        "facts": parser_arrays["facts"],
        "diagnostics": parser_arrays["diagnostics"],
        "coverage": {
            "selected_member_byte_verified": True,
            "parser_coverage": parser_output["coverage"],
            "parser_context_count": context_count,
            "parser_unit_count": unit_count,
            "parser_continuation_count": continuation_count,
            "parser_fact_count": fact_count,
            "parser_diagnostic_count": diagnostic_count,
            "package_member_set_complete": False,
            "filing_complete": False,
            "taxonomy_validation_complete": False,
            "relationship_validation_complete": False,
            "calculation_validation_complete": False,
            "xbrl_semantic_attested": False,
            "company_facts_attested": False,
            "archive_object_presence_attested": False,
        },
        "nonclaims": {
            "package_member_set_complete": False,
            "filing_complete": False,
            "taxonomy_validation_complete": False,
            "relationship_validation_complete": False,
            "calculation_validation_complete": False,
            "xbrl_semantic_attested": False,
            "company_facts_attested": False,
            "archive_object_presence_attested": False,
            "wrapper_raw_ledger_written": False,
            "wrapper_network_accessed": False,
            "wrapper_storage_accessed": False,
        },
    }
    record["extraction_id"] = _record_id(record)
    return IxbrlExtraction.from_dict(record)


_OBSERVED_RUNTIME_PARSER_FIELDS = frozenset(
    {"library", "library_version", "xml_library_version"}
)


def _semantic_replay_bytes(record: Mapping[str, Any]) -> bytes:
    """Compare replay semantics without erasing immutable artifact provenance.

    ``extraction_id`` deliberately commits the complete artifact, including
    observed runtime provenance.  A parser profile with the same stable
    semantic authority can, however, run under a later Python or Expat patch.
    Replay therefore removes only that observation from the comparison; the
    stored artifact itself is never rewritten or weakened at restore time.
    """
    value = _copy_json(
        record,
        field="ixbrl semantic replay record",
        budget=[HARD_MAX_JSON_NODES],
    )
    if not isinstance(value, dict):  # pragma: no cover - callers are sealed records.
        raise IxbrlExtractionError("ixbrl semantic replay record must be an object")
    value.pop("extraction_id", None)
    parser = value.get("parser")
    if not isinstance(parser, dict):  # pragma: no cover - callers are sealed records.
        raise IxbrlExtractionError("ixbrl semantic replay parser must be an object")
    for field in _OBSERVED_RUNTIME_PARSER_FIELDS:
        parser.pop(field, None)
    return canonical_json(value).encode("utf-8")


def verify_ixbrl_extraction_source(
    extraction: IxbrlExtraction | Mapping[str, Any],
    package: FilingPackage | Mapping[str, Any],
    retained_member_bytes: bytes,
) -> None:
    """Require external package and bytes, then replay the exact parser claim.

    This is a pure caller-supplied evidence comparison.  It does not read an
    archive object or attest its present existence; that authority belongs to
    the later ``ffatt_`` boundary with a verified archive readback contract.
    """
    result = _rehydrate_ixbrl_extraction_input(extraction)
    record = result.to_dict()
    rebuilt = build_ixbrl_extraction(
        package,
        record["source"]["member"]["document_name"],
        retained_member_bytes,
        computed_at=record["extraction"]["computed_at"],
    )
    if not hmac.compare_digest(
        _semantic_replay_bytes(rebuilt.to_dict()), _semantic_replay_bytes(result.to_dict())
    ):
        raise IxbrlExtractionError("source replay does not reproduce ixbrl extraction semantics")


def ixbrl_extraction_json_bytes(value: IxbrlExtraction | Mapping[str, Any]) -> bytes:
    return _rehydrate_ixbrl_extraction_input(value).to_json_bytes()


def _json_preflight_fail(message: str) -> None:
    raise IxbrlExtractionError(f"ixbrl extraction JSON preflight failed: {message}")


def _json_utf8_width(content: bytes, index: int) -> int:
    """Validate one UTF-8 scalar in a JSON string without allocating it."""
    lead = content[index]
    if lead < 0x80:
        return 1
    if 0xC2 <= lead <= 0xDF:
        width = 2
    elif 0xE0 <= lead <= 0xEF:
        width = 3
    elif 0xF0 <= lead <= 0xF4:
        width = 4
    else:
        _json_preflight_fail("invalid UTF-8 string byte")
    if index + width > len(content):
        _json_preflight_fail("truncated UTF-8 string byte sequence")
    tail = content[index + 1 : index + width]
    if any(byte < 0x80 or byte > 0xBF for byte in tail):
        _json_preflight_fail("invalid UTF-8 string byte sequence")
    # Reject overlong sequences, UTF-16 surrogate encodings, and values above
    # the Unicode scalar range before the standard decoder is asked to build a
    # potentially large object graph.
    if (lead == 0xE0 and tail[0] < 0xA0) or (lead == 0xED and tail[0] > 0x9F):
        _json_preflight_fail("invalid UTF-8 string scalar")
    if (lead == 0xF0 and tail[0] < 0x90) or (lead == 0xF4 and tail[0] > 0x8F):
        _json_preflight_fail("invalid UTF-8 string scalar")
    return width


def _preflight_ixbrl_json(content: bytes) -> None:
    """Bound JSON shape before ``json.loads`` can materialize a large tree.

    This is deliberately a lexical/structural gate, not a second JSON decoder.
    It accounts for every container, scalar, object key, decoded string byte,
    and nesting level with deterministic byte-level rules.  The standard
    decoder still owns duplicate-key capture, signed-64-bit integer admission,
    and the exact JSON value grammar used for the canonical artifact.
    """

    index = 0
    length = len(content)
    frames: list[dict[str, str]] = []
    root_state = "value"
    tokens = 0
    scalars = 0
    keys = 0
    nodes = 0
    decoded_string_bytes = 0

    def skip_whitespace(position: int) -> int:
        while position < length and content[position] in b" \t\r\n":
            position += 1
        return position

    def account(*, scalar: bool = False, key: bool = False) -> None:
        nonlocal tokens, scalars, keys, nodes
        tokens += 1
        if tokens > HARD_MAX_JSON_TOKENS:
            _json_preflight_fail("token safety limit exceeded")
        nodes += 1
        if nodes > HARD_MAX_JSON_NODES:
            _json_preflight_fail("node safety limit exceeded")
        if scalar:
            scalars += 1
            if scalars > HARD_MAX_JSON_SCALARS:
                _json_preflight_fail("scalar safety limit exceeded")
        if key:
            keys += 1
            if keys > HARD_MAX_JSON_OBJECT_KEYS:
                _json_preflight_fail("object-key safety limit exceeded")

    def consume_value() -> None:
        nonlocal root_state
        if frames:
            frame = frames[-1]
            if frame["kind"] == "object":
                if frame["state"] != "value":
                    _json_preflight_fail("object value is misplaced")
            elif frame["state"] != "value_or_end":
                _json_preflight_fail("array value is misplaced")
            frame["state"] = "comma_or_end"
            return
        if root_state != "value":
            _json_preflight_fail("multiple top-level values")
        root_state = "done"

    def parse_string(position: int) -> int:
        nonlocal decoded_string_bytes
        start = position
        position += 1  # opening quote
        decoded_length = 0
        while position < length:
            byte = content[position]
            if byte == 0x22:  # quote
                raw_length = position - start + 1
                if raw_length > HARD_MAX_JSON_STRING_TOKEN_BYTES:
                    _json_preflight_fail("string token safety limit exceeded")
                decoded_string_bytes += decoded_length
                if decoded_string_bytes > HARD_MAX_JSON_DECODED_STRING_BYTES:
                    _json_preflight_fail("decoded-string safety limit exceeded")
                return position + 1
            if byte == 0x5C:  # backslash
                if position + 1 >= length:
                    _json_preflight_fail("unterminated string escape")
                escaped = content[position + 1]
                if escaped in b'"\\/bfnrt':
                    decoded_length += 1
                    position += 2
                elif escaped == 0x75:  # u
                    if position + 6 > length or any(
                        character not in b"0123456789abcdefABCDEF"
                        for character in content[position + 2 : position + 6]
                    ):
                        _json_preflight_fail("invalid Unicode string escape")
                    # Four is a conservative upper bound for a decoded JSON
                    # unicode escape and retains a safe budget for surrogate
                    # pairs without allocating decoded strings here.
                    decoded_length += 4
                    position += 6
                else:
                    _json_preflight_fail("invalid string escape")
            else:
                if byte < 0x20:
                    _json_preflight_fail("unescaped control character in string")
                width = _json_utf8_width(content, position)
                decoded_length += width
                position += width
            if position - start > HARD_MAX_JSON_STRING_TOKEN_BYTES:
                _json_preflight_fail("string token safety limit exceeded")
            if decoded_length > HARD_MAX_JSON_STRING_TOKEN_BYTES:
                _json_preflight_fail("decoded string token safety limit exceeded")
        _json_preflight_fail("unterminated string")

    def parse_number(position: int) -> int:
        start = position
        if content[position] == 0x2D:  # minus
            position += 1
            if position >= length:
                _json_preflight_fail("truncated number")
        if position >= length or not (0x30 <= content[position] <= 0x39):
            _json_preflight_fail("invalid number")
        if content[position] == 0x30:
            position += 1
            if position < length and 0x30 <= content[position] <= 0x39:
                _json_preflight_fail("invalid leading-zero number")
        else:
            while position < length and 0x30 <= content[position] <= 0x39:
                position += 1
        if position < length and content[position] == 0x2E:  # decimal point
            position += 1
            decimal_start = position
            while position < length and 0x30 <= content[position] <= 0x39:
                position += 1
            if position == decimal_start:
                _json_preflight_fail("invalid fractional number")
        if position < length and content[position] in b"eE":
            position += 1
            if position < length and content[position] in b"+-":
                position += 1
            exponent_start = position
            while position < length and 0x30 <= content[position] <= 0x39:
                position += 1
            if position == exponent_start:
                _json_preflight_fail("invalid exponent number")
        if position - start > HARD_MAX_JSON_NUMBER_TOKEN_BYTES:
            _json_preflight_fail("number token safety limit exceeded")
        return position

    while True:
        index = skip_whitespace(index)
        if index >= length:
            break
        byte = content[index]
        if byte == 0x7B:  # {
            consume_value()
            account()
            if len(frames) + 1 > HARD_MAX_JSON_DEPTH:
                _json_preflight_fail("nesting safety limit exceeded")
            frames.append({"kind": "object", "state": "key_or_end"})
            index += 1
            continue
        if byte == 0x5B:  # [
            consume_value()
            account()
            if len(frames) + 1 > HARD_MAX_JSON_DEPTH:
                _json_preflight_fail("nesting safety limit exceeded")
            frames.append({"kind": "array", "state": "value_or_end"})
            index += 1
            continue
        if byte in (0x7D, 0x5D):  # } or ]
            if not frames:
                _json_preflight_fail("unmatched closing delimiter")
            frame = frames[-1]
            expected_kind = "object" if byte == 0x7D else "array"
            if frame["kind"] != expected_kind or frame["state"] not in {"key_or_end", "value_or_end", "comma_or_end"}:
                _json_preflight_fail("misplaced closing delimiter")
            frames.pop()
            index += 1
            continue
        if byte == 0x2C:  # comma
            if not frames or frames[-1]["state"] != "comma_or_end":
                _json_preflight_fail("misplaced comma")
            frames[-1]["state"] = "key_or_end" if frames[-1]["kind"] == "object" else "value_or_end"
            index += 1
            continue
        if byte == 0x3A:  # colon
            if not frames or frames[-1]["kind"] != "object" or frames[-1]["state"] != "colon":
                _json_preflight_fail("misplaced colon")
            frames[-1]["state"] = "value"
            index += 1
            continue
        if byte == 0x22:  # string
            end = parse_string(index)
            if frames and frames[-1]["kind"] == "object" and frames[-1]["state"] == "key_or_end":
                account(key=True)
                frames[-1]["state"] = "colon"
            else:
                consume_value()
                account(scalar=True)
            index = end
            continue
        if content.startswith(b"true", index) or content.startswith(b"false", index) or content.startswith(b"null", index):
            literal = b"true" if content.startswith(b"true", index) else b"false" if content.startswith(b"false", index) else b"null"
            end = index + len(literal)
            if end < length and content[end] not in b" \t\r\n,]}":
                _json_preflight_fail("invalid literal boundary")
            consume_value()
            account(scalar=True)
            index = end
            continue
        if content.startswith(b"NaN", index) or content.startswith(b"Infinity", index) or content.startswith(b"-Infinity", index):
            _json_preflight_fail("non-finite JSON constant")
        if byte == 0x2D or 0x30 <= byte <= 0x39:
            end = parse_number(index)
            if end < length and content[end] not in b" \t\r\n,]}":
                _json_preflight_fail("invalid number boundary")
            consume_value()
            account(scalar=True)
            index = end
            continue
        _json_preflight_fail("invalid JSON byte")

    if frames or root_state != "done":
        _json_preflight_fail("truncated JSON value")


def ixbrl_extraction_from_json_bytes(content: bytes) -> IxbrlExtraction:
    if not isinstance(content, bytes):
        raise IxbrlExtractionError("ixbrl extraction JSON must be bytes")
    if len(content) > HARD_MAX_FFXBRL_BYTES:
        raise IxbrlExtractionError("ixbrl extraction JSON exceeds byte safety limit")
    _preflight_ixbrl_json(content)

    def reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, item in pairs:
            if key in out:
                raise IxbrlExtractionError(f"duplicate JSON key: {key}")
            out[key] = item
        return out

    def reject_constant(value: str) -> None:
        raise IxbrlExtractionError(f"non-finite JSON constant: {value}")

    try:
        decoded = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=reject_pairs,
            parse_constant=reject_constant,
            parse_int=parse_json_int64,
        )
    except IxbrlExtractionError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise IxbrlExtractionError("ixbrl extraction JSON is not UTF-8 JSON") from exc
    if not isinstance(decoded, Mapping):
        raise IxbrlExtractionError("ixbrl extraction JSON must be an object")
    extraction = IxbrlExtraction.from_dict(decoded)
    if extraction.to_json_bytes() != content:
        raise IxbrlExtractionError("ixbrl extraction JSON is not canonically encoded")
    return extraction


__all__ = [
    "FFXBRL_ID_PREFIX",
    "FFXBRL_LIMITS",
    "FFXBRL_SCHEMA",
    "HARD_MAX_FFXBRL_BYTES",
    "IxbrlExtraction",
    "IxbrlExtractionError",
    "build_ixbrl_extraction",
    "ixbrl_extraction_from_json_bytes",
    "ixbrl_extraction_id_for",
    "ixbrl_extraction_json_bytes",
    "validate_ixbrl_extraction",
    "verify_ixbrl_extraction_source",
]
