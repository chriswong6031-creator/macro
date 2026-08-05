"""Canonical on-disk form for the immutable source-manifest ledger.

A manifest ID commits to the record's own canonical body, so the stored form
must be a function of that record alone.  Parquet cannot provide that.  pyarrow
unifies nested struct schemas across every row at write time, so a single new
row introducing a nested key that no existing row carries back-fills that key as
null into *all* pre-existing rows.  Their bodies then hash differently and the
IDs they were written with stop matching.

That is not a hypothetical.  ``filing.file_number_provenance`` and
``filing.collection_scope`` (added by #4243, after the last ledger commit)
invalidated all 1258 retained rows on the next read, which is what failed
``scripts.compile_capital_structure_events`` every night from 2026-08-05.  The
drifted file is never committed, so each night restored the clean ledger,
re-drifted it identically, and failed again -- deterministic, not flaky.

JSON Lines stores each record independently: one canonical JSON object per
line, no cross-row schema to unify.  The bytes on disk are exactly the canonical
body the ID commits to, so identity survives any future schema growth without a
migration or an ID re-pin.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import os
from pathlib import Path
from typing import Any

from .source_identity import (
    ManifestIdentityError,
    canonical_manifest_bytes,
    validate_manifest_ledger,
)


SOURCE_LEDGER_FILENAME = "source_manifest.jsonl"
LEGACY_SOURCE_LEDGER_FILENAME = "source_manifest.parquet"


def source_ledger_path(root: Path) -> Path:
    """Return the canonical ledger path inside a capital-structure data root."""
    return Path(root) / SOURCE_LEDGER_FILENAME


def encode_source_ledger(records: Sequence[Mapping[str, Any]]) -> bytes:
    """Return canonical JSON Lines bytes, one full record per line.

    Deliberately does not validate: callers that build fixtures need to write
    ledgers this repository's identity law rejects.  ``write_source_ledger`` is
    the validating boundary.
    """
    if isinstance(records, (str, bytes, Mapping)):
        raise TypeError("source ledger records must be a sequence of mappings")
    lines = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise TypeError(f"source ledger row {index}: record must be a mapping")
        lines.append(canonical_manifest_bytes(record))
    return b"".join(line + b"\n" for line in lines)


def decode_source_ledger(body: bytes, *, label: str) -> list[dict[str, Any]]:
    """Parse canonical JSON Lines bytes into full manifest records.

    Strict by construction: a blank line, a trailing partial line, or a non-object
    line is a corrupt ledger, never a row to skip.
    """
    if not isinstance(body, (bytes, bytearray)):
        raise TypeError("source ledger body must be bytes")
    text = bytes(body).decode("utf-8")
    if not text:
        return []
    if not text.endswith("\n"):
        raise ManifestIdentityError(
            f"source ledger {label}: final row is not newline-terminated"
        )
    records: list[dict[str, Any]] = []
    for index, line in enumerate(text[:-1].split("\n")):
        if not line.strip():
            raise ManifestIdentityError(f"source ledger {label} row {index}: blank line")
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ManifestIdentityError(
                f"source ledger {label} row {index}: unreadable JSON: {exc}"
            ) from exc
        if not isinstance(record, dict):
            raise ManifestIdentityError(
                f"source ledger {label} row {index}: record must be a JSON object"
            )
        records.append(record)
    return records


def read_source_ledger(path: Path) -> list[dict[str, Any]]:
    """Return every retained manifest record, or ``[]`` when none is retained.

    A leftover parquet ledger is a hard error rather than a silent empty read:
    that file holds real retained provenance, and treating it as absent would
    drop the whole immutable prefix.
    """
    path = Path(path)
    if not path.exists():
        legacy = path.parent / LEGACY_SOURCE_LEDGER_FILENAME
        if legacy.exists():
            raise ManifestIdentityError(
                f"source ledger {legacy} is the superseded parquet form; migrate it to "
                f"{SOURCE_LEDGER_FILENAME} (scripts/migrate_source_manifest_to_jsonl.py)"
            )
        return []
    try:
        body = path.read_bytes()
    except OSError as exc:
        raise ManifestIdentityError(f"source ledger unreadable: {path}: {exc}") from exc
    return decode_source_ledger(body, label=str(path))


def write_source_ledger(
    records: Sequence[Mapping[str, Any]], path: Path, *, validate: bool = True,
) -> None:
    """Atomically persist the ledger, refusing to write a drifted prefix.

    Validation runs at the write boundary on purpose.  The failure this format
    replaces was only ever observable one process later, in the compiler; a
    ledger that cannot be re-read as the IDs it carries must not reach disk.
    """
    path = Path(path)
    if validate:
        validate_manifest_ledger(list(records))
    body = encode_source_ledger(records)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.jsonl")
    tmp.write_bytes(body)
    os.replace(tmp, path)
