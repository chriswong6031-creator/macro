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
from typing import Any


MANIFEST_ID_PREFIX = "manifest:cs:"


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
