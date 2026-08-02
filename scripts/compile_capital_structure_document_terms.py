"""Compile row/security-scoped SEC registration-fee-table facts into an immutable ledger.

The compiler is deliberately source-document and fee-table-row scoped. It reads retained
complete-submission bytes through the manifest's named object-store namespace,
then transcribes only explicitly displayed, dimension-safe fee-table cells. It does not build
instruments, aggregate registrations, calculate capacity, or create a
dilution/trading/Prophet signal.

The compiler never fetches SEC HTTP endpoints. It may read already-retained
content-addressed source objects from the configured R2/local source store.

Usage:
    python -m scripts.compile_capital_structure_document_terms [--rebuild]
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

import pandas as pd

from engine.capital_structure.document_terms import (
    DOCUMENT_TERM_SCHEMA,
    DocumentTermCompileDegraded,
    compile_document_term_records,
    observation_id_for,
    validate_observation_source_binding,
    validate_document_term_history,
)
from engine.capital_structure.source_identity import (
    validate_manifest_content_binding,
    validate_manifest_ledger,
)
from engine.capital_structure.source_store import build_source_stores


DOCUMENT_TERM_COLUMNS = [
    "observation_id", "logical_observation_id", "issuer_id", "accession", "form",
    "source_manifest_id", "term_name", "state", "available_at",
    "correction_version", "observation_json",
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _data_root() -> Path:
    from lib import config

    return config.data_dir() / "capital_structure"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _native(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_native(item) for item in value]
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes, bytearray)):
        try:
            converted = value.tolist()
            if converted is not value:
                return _native(converted)
        except Exception:  # noqa: BLE001
            pass
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item") and not isinstance(value, (str, bytes, bytearray)):
        try:
            return value.item()
        except Exception:  # noqa: BLE001
            pass
    return value


def dataframe_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [_native(row) for row in frame.to_dict(orient="records")]


def _load_contract(name: str) -> dict[str, Any]:
    return json.loads((_repo_root() / "contracts" / name).read_text(encoding="utf-8"))


def _validate_schema(record: Mapping[str, Any], schema: Mapping[str, Any], label: str) -> None:
    from jsonschema import Draft202012Validator, FormatChecker

    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(record))
    if errors:
        joined = "; ".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors[:5]
        )
        raise ValueError(f"{label} contract violation: {joined}")


def _load_existing_observations(path: Path, schema: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    frame = pd.read_parquet(path)
    if frame.columns.tolist() != DOCUMENT_TERM_COLUMNS:
        raise ValueError(
            "document-term ledger columns must exactly equal "
            f"{DOCUMENT_TERM_COLUMNS}; got {frame.columns.tolist()}"
        )
    observations: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
        raw = row["observation_json"]
        if not isinstance(raw, str) or not raw:
            raise ValueError(f"document-term ledger row {index} lacks canonical observation_json")
        try:
            observation = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"document-term ledger row {index} has malformed observation_json") from exc
        if not isinstance(observation, Mapping):
            raise ValueError(f"document-term ledger row {index} observation_json must be an object")
        _validate_schema(observation, schema, f"document-term ledger row {index}")
        if str(observation.get("observation_id") or "") != observation_id_for(observation):
            raise ValueError(f"document-term ledger row {index} observation_id digest mismatch")
        expected = {
            "observation_id": observation.get("observation_id"),
            "logical_observation_id": observation.get("logical_observation_id"),
            "issuer_id": observation.get("issuer_id"),
            "accession": (observation.get("filing") or {}).get("accession"),
            "form": (observation.get("filing") or {}).get("form"),
            "source_manifest_id": (observation.get("document") or {}).get("source_manifest_id"),
            "term_name": (observation.get("term") or {}).get("name"),
            "state": (observation.get("state") or {}).get("disposition"),
            "available_at": (observation.get("point_in_time") or {}).get("available_at"),
            "correction_version": int((observation.get("version") or {}).get("correction_version") or 0),
        }
        for column, value in expected.items():
            actual = _native(row[column])
            if column == "correction_version" and actual is not None:
                actual = int(actual)
            if actual != value:
                raise ValueError(
                    f"document-term ledger row {index} denormalized {column} mismatch: {actual!r} != {value!r}"
                )
        if raw != _canonical_json(observation):
            raise ValueError(f"document-term ledger row {index} observation_json is not canonical")
        observations.append(dict(observation))
    validate_document_term_history(observations)
    return observations


def _validate_observation_lineage(
    observations: Sequence[Mapping[str, Any]], manifests: Sequence[Mapping[str, Any]],
    schema: Mapping[str, Any], *, source_reader,
) -> None:
    by_manifest = {str(row["manifest_id"]): row for row in manifests}
    source_cache: dict[str, bytes | None] = {}
    for index, raw in enumerate(observations):
        observation = dict(raw)
        _validate_schema(observation, schema, f"output document-term {index}")
        document = observation.get("document") or {}
        evidence = observation.get("evidence") or {}
        manifest_id = str(document.get("source_manifest_id") or "")
        manifest = by_manifest.get(manifest_id)
        if manifest is None:
            raise ValueError(f"output document-term {index} source manifest is absent")
        source_document = manifest.get("document") or {}
        if (
            str(evidence.get("source_manifest_id") or "") != manifest_id
            or str(evidence.get("source_document_sha256") or "").lower()
            != str(source_document.get("content_sha256") or "").lower()
            or str(document.get("content_sha256") or "").lower()
            != str(source_document.get("content_sha256") or "").lower()
        ):
            raise ValueError(f"output document-term {index} has detached source evidence")
        if (source_document.get("document_role") or "") != "complete_submission":
            raise ValueError(f"output document-term {index} source is not a complete submission")
        needs_source_bytes = bool(document.get("child_document_type")) or any(
            str((span or {}).get("locator_type") or "") != "document"
            for span in evidence.get("spans") or []
        )
        if needs_source_bytes and manifest_id not in source_cache:
            source_cache[manifest_id] = source_reader(manifest)
        source_bytes = source_cache.get(manifest_id)
        if needs_source_bytes and source_bytes is None:
            raise ValueError(f"output document-term {index} source bytes are unavailable")
        validate_observation_source_binding(observation, manifest, source_bytes)
    validate_document_term_history(observations)


def _to_frame(observations: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for observation in observations:
        filing = observation.get("filing") or {}
        document = observation.get("document") or {}
        term = observation.get("term") or {}
        state = observation.get("state") or {}
        point_in_time = observation.get("point_in_time") or {}
        version = observation.get("version") or {}
        rows.append({
            "observation_id": observation["observation_id"],
            "logical_observation_id": observation["logical_observation_id"],
            "issuer_id": observation["issuer_id"],
            "accession": filing["accession"], "form": filing["form"],
            "source_manifest_id": document["source_manifest_id"],
            "term_name": term["name"], "state": state["disposition"],
            "available_at": point_in_time["available_at"],
            "correction_version": int(version["correction_version"]),
            "observation_json": _canonical_json(observation),
        })
    return pd.DataFrame(rows, columns=DOCUMENT_TERM_COLUMNS)


def _atomic_write(frame: pd.DataFrame, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp.parquet", dir=target.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        frame.to_parquet(temporary, index=False)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def _source_reader_for_store(source_store):
    if isinstance(source_store, Mapping):
        stores = dict(source_store)
    elif source_store is None:
        stores = {}
    else:
        stores = {str(source_store.store_id): source_store}

    def read(manifest: Mapping[str, Any]) -> bytes | None:
        storage = manifest.get("storage") or {}
        document = manifest.get("document") or {}
        # A configured default R2 bucket must not silently masquerade as another
        # stable store namespace.  The manifest's namespace is part of the source
        # identity, not optional deployment decoration.
        source_store = stores.get(str(storage.get("store_id") or ""))
        if source_store is None:
            return None
        return source_store.get_verified(
            str(storage.get("object_key") or ""),
            str(document.get("content_sha256") or "").lower(),
        )
    return read


def compile_from_disk(
    *,
    root: Path | None = None,
    generated_at: str | None = None,
    source_store=None,
    rebuild: bool = False,
) -> dict[str, Any]:
    """Compile append-only direct term rows without SEC fetches.

    Source bytes are obtained only through the manifest-addressed local/R2 store,
    where an R2 read is an integrity-checked evidence retrieval rather than a new
    SEC acquisition.
    """
    root = root or _data_root()
    manifest_path = root / "source_manifest.parquet"
    ledger_path = root / "document_term_observations.parquet"
    manifest_schema = _load_contract("capital_structure_source_manifest.schema.json")
    observation_schema = _load_contract("capital_structure_document_term_observation.schema.json")
    manifests = dataframe_records(pd.read_parquet(manifest_path)) if manifest_path.exists() else []
    for index, manifest in enumerate(manifests):
        _validate_schema(manifest, manifest_schema, f"source manifest {index}")
        validate_manifest_content_binding(manifest)
    validate_manifest_ledger(manifests)
    existing = _load_existing_observations(ledger_path, observation_schema)
    store = source_store if source_store is not None else build_source_stores()
    base_reader = _source_reader_for_store(store)
    source_cache: dict[str, bytes | None] = {}

    def source_reader(manifest: Mapping[str, Any]) -> bytes | None:
        manifest_id = str(manifest.get("manifest_id") or "")
        if manifest_id not in source_cache:
            source_cache[manifest_id] = base_reader(manifest)
        return source_cache[manifest_id]

    result = compile_document_term_records(
        manifests,
        source_reader=source_reader,
        existing_observations=existing,
        generated_at=generated_at or _now_iso(),
        rebuild=rebuild,
    )
    observations = result["observations"]
    _validate_observation_lineage(
        observations, manifests, observation_schema, source_reader=source_reader,
    )
    _atomic_write(_to_frame(observations), ledger_path)
    return {"status": "ok", **result["counts"], "path": str(ledger_path)}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rebuild", action="store_true",
        help="re-read every retained in-scope submission to deliberately create correction versions when parsing changes",
    )
    args = parser.parse_args(argv)
    try:
        result = compile_from_disk(rebuild=args.rebuild)
    except DocumentTermCompileDegraded as exc:
        print(json.dumps({"status": "degraded", "failures": exc.failures}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
