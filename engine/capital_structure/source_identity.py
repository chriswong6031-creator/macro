"""Canonical identity and ordered-prefix receipts for source manifests.

The manifest ID commits to the entire canonical manifest body except the ID
field itself.  This module is deliberately pure and dependency-free so both
the online collector and offline compiler can enforce the same identity law.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
import hashlib
import hmac
import json
import math
import re
from typing import Any


MANIFEST_ID_PREFIX = "manifest:cs:"
_SEC_DOCUMENT_ACCESSION_RE = re.compile(
    br"<SEC-DOCUMENT>\s*([0-9]{10}-[0-9]{2}-[0-9]{6})(?:\.txt)?",
    re.IGNORECASE,
)
_SEC_HEADER_BLOCK_RE = re.compile(
    br"<SEC-HEADER>\s*(.*?)(?:</SEC-HEADER>|<DOCUMENT>)",
    re.IGNORECASE | re.DOTALL,
)
_SEC_HEADER_CIK_RE = re.compile(
    br"CENTRAL\s+INDEX\s+KEY:\s*([0-9]{1,10})",
    re.IGNORECASE,
)
_SEC_HEADER_FORM_RE = re.compile(
    br"CONFORMED\s+SUBMISSION\s+TYPE:\s*([^\r\n<]+)",
    re.IGNORECASE,
)
_SEC_FORM_RE = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)*(?: [A-Z0-9]+)*(?:/[A-Z0-9]+)?$")


class ManifestIdentityError(ValueError):
    """A source manifest or ordered ledger violates immutable identity law."""


def _native(value: Any) -> Any:
    """Normalize Arrow/numpy-like containers without importing those packages."""
    if isinstance(value, Mapping):
        return {str(key): _native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_native(item) for item in value]
    if isinstance(value, set):
        raise TypeError("sets are not canonical manifest values")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("non-finite numbers are not canonical manifest values")
        return value
    if hasattr(value, "tolist"):
        converted = value.tolist()
        if converted is not value:
            return _native(converted)
    if hasattr(value, "item"):
        converted = value.item()
        if converted is not value:
            return _native(converted)
    raise TypeError(f"unsupported canonical manifest value: {type(value).__name__}")


def canonical_manifest_bytes(record: Mapping[str, Any]) -> bytes:
    """Return canonical UTF-8 JSON for one full manifest record."""
    return json.dumps(
        _native(record),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def manifest_id_for(record: Mapping[str, Any]) -> str:
    """Return ``manifest:cs:<sha256>`` over the body excluding ``manifest_id``."""
    body = dict(record)
    body.pop("manifest_id", None)
    digest = hashlib.sha256(canonical_manifest_bytes(body)).hexdigest()
    return MANIFEST_ID_PREFIX + digest


def validate_manifest_identity(record: Mapping[str, Any]) -> None:
    """Fail closed unless the supplied ID exactly commits to the full body."""
    actual = record.get("manifest_id")
    expected = manifest_id_for(record)
    if not isinstance(actual, str) or not hmac.compare_digest(actual, expected):
        raise ManifestIdentityError(
            f"source manifest identity mismatch: expected {expected}, got {actual!r}"
        )


def validate_manifest_ledger(records: Sequence[Mapping[str, Any]]) -> None:
    """Validate every identity and reject duplicate or divergent global IDs."""
    seen: dict[str, bytes] = {}
    for index, record in enumerate(records):
        try:
            validate_manifest_identity(record)
            encoded = canonical_manifest_bytes(record)
        except (ManifestIdentityError, TypeError, ValueError) as exc:
            raise ManifestIdentityError(f"source ledger row {index}: {exc}") from exc
        manifest_id = str(record["manifest_id"])
        prior = seen.get(manifest_id)
        if prior is not None:
            reason = "divergent" if prior != encoded else "duplicate"
            raise ManifestIdentityError(
                f"source ledger row {index}: {reason} global manifest_id {manifest_id}"
            )
        seen[manifest_id] = encoded


def validate_manifest_content_binding(record: Mapping[str, Any]) -> None:
    """Require a manifest's hash, object key, and root span to bind the same bytes.

    Schema validation checks field shapes and immutable identity checks the full
    manifest body. This semantic guard prevents a well-formed, re-signed body
    from pointing one of those three coordinates at a different object.
    """
    document = record.get("document") or {}
    storage = record.get("storage") or {}
    digest = str(document.get("content_sha256") or "").lower()
    if not _is_sha256(digest):
        raise ManifestIdentityError("document.content_sha256 must be lowercase SHA-256")
    if str(document.get("root_locator") or "").lower() != f"sha256:{digest}":
        raise ManifestIdentityError("document.root_locator must bind document.content_sha256")
    object_key = str(storage.get("object_key") or "")
    if object_key != f"capital_structure/sec/sha256/{digest[:2]}/{digest}":
        raise ManifestIdentityError("storage.object_key must bind document.content_sha256")
    byte_length = document.get("byte_length")
    if isinstance(byte_length, bool) or not isinstance(byte_length, int) or byte_length < 0:
        raise ManifestIdentityError("document.byte_length must be a non-negative integer")
    expected_locator = f"bytes:0-{byte_length}"
    matches = [
        span for span in (record.get("spans") or [])
        if isinstance(span, Mapping)
        and str(span.get("locator_type") or "") == "document"
        and str(span.get("locator") or "") == expected_locator
        and str(span.get("text_sha256") or "").lower() == digest
    ]
    if not matches:
        raise ManifestIdentityError("manifest lacks exact document root span")


def _canonical_cik(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw.isdigit() or len(raw) > 10:
        raise ManifestIdentityError("SEC CIK must be one to ten decimal digits")
    return raw.zfill(10)


def _canonical_sec_form(value: Any) -> str:
    """Normalize only case and whitespace; never collapse amendment status."""
    raw = " ".join(str(value or "").strip().upper().split())
    if not raw or _SEC_FORM_RE.fullmatch(raw) is None:
        raise ManifestIdentityError("SEC submission form is malformed")
    return raw


def _complete_submission_header(raw: bytes) -> bytes:
    if len(re.findall(br"<SEC-HEADER>", raw, re.IGNORECASE)) != 1:
        raise ManifestIdentityError("SEC complete-submission must contain exactly one SEC header")
    headers = _SEC_HEADER_BLOCK_RE.findall(raw)
    if len(headers) != 1:
        raise ManifestIdentityError("SEC complete-submission must contain exactly one SEC header")
    return headers[0]


def validate_manifest_retained_bytes_binding(
    record: Mapping[str, Any], raw: bytes | None,
) -> None:
    """Bind SEC manifest identity fields to the retained complete-submission bytes.

    A manifest ID is an immutable *commitment*, not a signature.  Rehashing a
    forged envelope must therefore still fail against the SEC submission header:
    the accession embeds the filing CIK, and the optional SEC-header CIK (when
    present) must agree.  This closes the otherwise self-consistent
    ``manifest -> direct observation -> candidate`` issuer rewrite path.
    """
    validate_manifest_content_binding(record)
    if not isinstance(raw, bytes):
        raise ManifestIdentityError("retained source bytes are required")
    document = record.get("document") or {}
    expected_digest = str(document.get("content_sha256") or "").lower()
    if hashlib.sha256(raw).hexdigest() != expected_digest:
        raise ManifestIdentityError("retained source bytes fail manifest digest")
    if (
        str(record.get("source_system") or "") != "sec_edgar"
        or str(document.get("document_role") or "") != "complete_submission"
    ):
        return

    accession_match = _SEC_DOCUMENT_ACCESSION_RE.search(raw)
    if accession_match is None:
        raise ManifestIdentityError("SEC complete-submission header lacks a canonical accession")
    source_accession = accession_match.group(1).decode("ascii")
    filing = record.get("filing") or {}
    if str(filing.get("accession") or "") != source_accession:
        raise ManifestIdentityError("manifest filing.accession is detached from SEC submission header")
    source_id = str(record.get("source_id") or "")
    expected_source_id = f"{source_accession}:0:complete-submission.txt"
    if source_id != expected_source_id:
        raise ManifestIdentityError("manifest source_id is detached from SEC submission header")

    header = _complete_submission_header(raw)
    header_forms = _SEC_HEADER_FORM_RE.findall(header)
    if len(header_forms) != 1:
        raise ManifestIdentityError(
            "SEC complete-submission header must contain exactly one CONFORMED SUBMISSION TYPE"
        )
    header_form = _canonical_sec_form(header_forms[0].decode("ascii", errors="strict"))
    if _canonical_sec_form(filing.get("form")) != header_form:
        raise ManifestIdentityError("manifest filing.form is detached from SEC submission header")

    accession_cik = _canonical_cik(source_accession.split("-", 1)[0])
    header_ciks = {
        _canonical_cik(match.group(1).decode("ascii"))
        for match in _SEC_HEADER_CIK_RE.finditer(header)
    }
    if header_ciks and header_ciks != {accession_cik}:
        raise ManifestIdentityError("SEC header CIK conflicts with SEC submission accession")
    issuer = record.get("issuer") or {}
    if _canonical_cik(issuer.get("cik")) != accession_cik:
        raise ManifestIdentityError("manifest issuer.cik is detached from SEC submission header")
    if str(issuer.get("issuer_id") or "") != f"sec:cik:{accession_cik}":
        raise ManifestIdentityError("manifest issuer_id is detached from SEC submission header")


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def merge_manifest_ledgers(
    existing: Sequence[Mapping[str, Any]],
    fresh: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Append new immutable rows while preserving the exact existing prefix."""
    validate_manifest_ledger(existing)
    out = [_native(record) for record in existing]
    by_id = {
        str(record["manifest_id"]): canonical_manifest_bytes(record)
        for record in out
    }
    fresh_seen: set[str] = set()
    for index, raw in enumerate(fresh):
        record = _native(raw)
        try:
            validate_manifest_identity(record)
        except ManifestIdentityError as exc:
            raise ManifestIdentityError(f"fresh source row {index}: {exc}") from exc
        manifest_id = str(record["manifest_id"])
        encoded = canonical_manifest_bytes(record)
        if manifest_id in fresh_seen:
            raise ManifestIdentityError(
                f"fresh source row {index}: duplicate global manifest_id {manifest_id}"
            )
        fresh_seen.add(manifest_id)
        prior = by_id.get(manifest_id)
        if prior is not None:
            if prior != encoded:
                raise ManifestIdentityError(
                    f"fresh source row {index}: divergent global manifest_id {manifest_id}"
                )
            continue
        by_id[manifest_id] = encoded
        out.append(record)
    return out


def source_ledger_prefix_hash(
    records: Sequence[Mapping[str, Any]], count: int | None = None
) -> str:
    """Return lowercase SHA-256 hex over canonical full records in prefix order."""
    validate_manifest_ledger(records)
    if count is None:
        count = len(records)
    if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= len(records):
        raise ValueError("count must select a valid source-ledger prefix")
    canonical_prefix = [_native(record) for record in records[:count]]
    payload = json.dumps(
        canonical_prefix,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
