"""Compile immutable, pre-instrument candidate terms from the direct-term ledger.

This offline compiler has exactly one input authority: the locally validated
``capital_structure.document_term_observation/v1`` ledger.  It does not fetch
SEC data, consult market data, or match a row to an instrument.  Its output is
context-only provenance for the later identity-resolution lane.

Usage:
    python -m scripts.compile_capital_structure_instrument_candidate_terms
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any

import pandas as pd

from engine.capital_structure.instrument_candidates import (
    candidate_term_id_for,
    compile_candidate_term_records,
    validate_candidate_term_structure,
)
from engine.capital_structure.source_store import build_source_stores
from scripts.compile_capital_structure_document_terms import _source_reader_for_store


DOCUMENT_TERM_COLUMNS = [
    "observation_id", "logical_observation_id", "issuer_id", "accession", "form",
    "source_manifest_id", "term_name", "state", "available_at",
    "correction_version", "observation_json",
]
CANDIDATE_TERM_COLUMNS = [
    "candidate_term_id", "logical_candidate_term_id", "issuer_id", "accession", "form",
    "source_manifest_id", "direct_observation_id", "candidate_family", "supply_role",
    "state", "available_at", "correction_version", "candidate_term_json",
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


def _load_document_terms(path: Path, schema: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    frame = pd.read_parquet(path)
    if frame.columns.tolist() != DOCUMENT_TERM_COLUMNS:
        raise ValueError(
            "document-term input ledger columns must exactly equal "
            f"{DOCUMENT_TERM_COLUMNS}; got {frame.columns.tolist()}"
        )
    observations: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
        raw = row["observation_json"]
        if not isinstance(raw, str) or not raw:
            raise ValueError(f"document-term input ledger row {index} lacks canonical observation_json")
        try:
            observation = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"document-term input ledger row {index} has malformed observation_json") from exc
        if not isinstance(observation, Mapping):
            raise ValueError(f"document-term input ledger row {index} observation_json must be an object")
        _validate_schema(observation, schema, f"document-term input ledger row {index}")
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
                    f"document-term input ledger row {index} denormalized {column} mismatch: {actual!r} != {value!r}"
                )
        if raw != _canonical_json(observation):
            raise ValueError(f"document-term input ledger row {index} observation_json is not canonical")
        observations.append(dict(observation))
    return observations


def _load_existing_candidates(path: Path, schema: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    frame = pd.read_parquet(path)
    if frame.columns.tolist() != CANDIDATE_TERM_COLUMNS:
        raise ValueError(
            "candidate-term ledger columns must exactly equal "
            f"{CANDIDATE_TERM_COLUMNS}; got {frame.columns.tolist()}"
        )
    records: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
        raw = row["candidate_term_json"]
        if not isinstance(raw, str) or not raw:
            raise ValueError(f"candidate-term ledger row {index} lacks canonical candidate_term_json")
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"candidate-term ledger row {index} has malformed candidate_term_json") from exc
        if not isinstance(record, Mapping):
            raise ValueError(f"candidate-term ledger row {index} candidate_term_json must be an object")
        _validate_schema(record, schema, f"candidate-term ledger row {index}")
        if str(record.get("candidate_term_id") or "") != candidate_term_id_for(record):
            raise ValueError(f"candidate-term ledger row {index} candidate_term_id digest mismatch")
        source = record.get("source_term") or {}
        candidate = record.get("candidate") or {}
        expected = {
            "candidate_term_id": record.get("candidate_term_id"),
            "logical_candidate_term_id": record.get("logical_candidate_term_id"),
            "issuer_id": record.get("issuer_id"),
            "accession": (record.get("filing") or {}).get("accession"),
            "form": (record.get("filing") or {}).get("form"),
            "source_manifest_id": (record.get("document") or {}).get("source_manifest_id"),
            "direct_observation_id": source.get("observation_id"),
            "candidate_family": candidate.get("family"),
            "supply_role": candidate.get("supply_role"),
            "state": (candidate.get("state") or {}).get("disposition"),
            "available_at": (record.get("point_in_time") or {}).get("available_at"),
            "correction_version": int((record.get("version") or {}).get("correction_version") or 0),
        }
        for column, value in expected.items():
            actual = _native(row[column])
            if column == "correction_version" and actual is not None:
                actual = int(actual)
            if actual != value:
                raise ValueError(
                    f"candidate-term ledger row {index} denormalized {column} mismatch: {actual!r} != {value!r}"
                )
        if raw != _canonical_json(record):
            raise ValueError(f"candidate-term ledger row {index} candidate_term_json is not canonical")
        records.append(dict(record))
    # Source binding is deliberately deferred until compile_from_disk has loaded
    # the direct ledger's manifests and retained-byte reader.  This local pass
    # only protects safe decoding of the candidate Parquet envelope.
    validate_candidate_term_structure(records)
    return records


def _to_frame(records: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in records:
        filing = record.get("filing") or {}
        document = record.get("document") or {}
        source = record.get("source_term") or {}
        candidate = record.get("candidate") or {}
        state = candidate.get("state") or {}
        point_in_time = record.get("point_in_time") or {}
        version = record.get("version") or {}
        rows.append({
            "candidate_term_id": record["candidate_term_id"],
            "logical_candidate_term_id": record["logical_candidate_term_id"],
            "issuer_id": record["issuer_id"],
            "accession": filing["accession"], "form": filing["form"],
            "source_manifest_id": document["source_manifest_id"],
            "direct_observation_id": source["observation_id"],
            "candidate_family": candidate["family"], "supply_role": candidate["supply_role"],
            "state": state["disposition"], "available_at": point_in_time["available_at"],
            "correction_version": int(version["correction_version"]),
            "candidate_term_json": _canonical_json(record),
        })
    return pd.DataFrame(rows, columns=CANDIDATE_TERM_COLUMNS)


def _atomic_write(frame: pd.DataFrame, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp.parquet", dir=target.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        frame.to_parquet(temporary, index=False)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def compile_from_disk(
    *,
    root: Path | None = None,
    generated_at: str | None = None,
    source_as_of: str | None = None,
    source_store=None,
) -> dict[str, Any]:
    """Compile from a direct ledger after re-verifying its source authority."""
    root = root or _data_root()
    manifest_path = root / "source_manifest.parquet"
    source_path = root / "document_term_observations.parquet"
    target_path = root / "instrument_candidate_terms.parquet"
    if not source_path.exists():
        return {
            "status": "unavailable",
            "reason": "document_term_ledger_absent",
            "input_path": str(source_path),
            "path": str(target_path),
        }
    direct_schema = _load_contract("capital_structure_document_term_observation.schema.json")
    candidate_schema = _load_contract("capital_structure_instrument_candidate_term.schema.json")
    if not manifest_path.exists():
        raise ValueError("source-manifest ledger is required to verify document-term authority")
    manifests = dataframe_records(pd.read_parquet(manifest_path))
    direct_terms = _load_document_terms(source_path, direct_schema)
    existing = _load_existing_candidates(target_path, candidate_schema)
    store = source_store if source_store is not None else build_source_stores()
    result = compile_candidate_term_records(
        direct_terms,
        source_manifests=manifests,
        source_reader=_source_reader_for_store(store),
        existing_candidate_terms=existing,
        generated_at=generated_at or _now_iso(),
        source_as_of=source_as_of,
    )
    _atomic_write(_to_frame(result["observations"]), target_path)
    return {"status": "ok", **result["counts"], "source_as_of": result["source_as_of"], "path": str(target_path)}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-as-of", help="only project direct terms visible by this ISO-8601 system time")
    args = parser.parse_args(argv)
    print(json.dumps(compile_from_disk(source_as_of=args.source_as_of), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
