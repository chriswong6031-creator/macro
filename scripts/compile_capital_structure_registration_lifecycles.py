"""Compile the Capital Structure observed registration lifecycle truth plane.

The writer is offline and fail-closed. It verifies the telemetry-last Capital
Structure event generation before reading its immutable event/edge ledgers,
then atomically replaces one canonical JSON artifact. It performs no source
discovery, no network I/O, and no dashboard or workflow publication.

Usage:
    python3 -m scripts.compile_capital_structure_registration_lifecycles
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

from engine.capital_structure.registration_lifecycle import (
    compile_registration_lifecycles,
    validate_registration_lifecycle_bundle,
)
from scripts.compile_capital_structure_events import (
    EDGE_COLUMNS,
    _load_contract,
    _load_existing_edges,
    _load_existing_events,
    _validate_committed_generation,
    dataframe_records,
)


def _data_root() -> Path:
    from lib import config

    return config.data_dir() / "capital_structure"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unreadable JSON object: {path}") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"JSON root must be an object: {path}")
    return dict(value)


def _atomic_write(payload: bytes, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, staged_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    staged = Path(staged_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged, target)
    finally:
        if staged.exists():
            staged.unlink()


def compile_from_disk(
    *,
    root: Path | None = None,
    output_path: Path | None = None,
    as_of: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Verify one event-spine generation and atomically write its truth plane."""
    root = root or _data_root()
    output_path = output_path or (root / "registration_lifecycles.json")
    produced_at = generated_at or _now_iso()

    manifest_path = root / "source_manifest.parquet"
    manifests = (
        dataframe_records(pd.read_parquet(manifest_path))
        if manifest_path.exists()
        else []
    )
    telemetry_path = root / "telemetry.json"
    telemetry = (
        _read_json_object(telemetry_path)
        if telemetry_path.exists()
        else {
            "status": "missing",
            "as_of": None,
            "generation_id": None,
            "artifact_hashes": {},
        }
    )
    has_generation = _validate_committed_generation(
        root, _load_contract("telemetry"), manifests
    )

    if has_generation:
        event_path = root / "event_versions.parquet"
        edge_path = root / "event_edges.parquet"
        events = _load_existing_events(
            pd.read_parquet(event_path), _load_contract("event")
        )
        edge_frame = pd.read_parquet(edge_path)
        if edge_frame.columns.tolist() != EDGE_COLUMNS:
            raise ValueError("event edge ledger columns changed before lifecycle compile")
        edges = _load_existing_edges(edge_frame, _load_contract("edge"))
        counts = telemetry.get("counts") or {}
        if int(counts.get("event_versions", -1)) != len(events):
            raise ValueError(
                "registration lifecycle input event count does not match telemetry"
            )
        if int(counts.get("event_edges", -1)) != len(edges):
            raise ValueError(
                "registration lifecycle input edge count does not match telemetry"
            )
    else:
        events, edges = [], []

    lifecycle_as_of = as_of or telemetry.get("as_of") or produced_at
    artifact_hashes = telemetry.get("artifact_hashes") or {}
    bundle = compile_registration_lifecycles(
        events,
        edges,
        str(lifecycle_as_of),
        produced_at,
        source_generation={
            "generation_id": telemetry.get("generation_id"),
            "as_of": telemetry.get("as_of"),
            "status": telemetry.get("status") or "missing",
            "artifact_hashes": {
                "event_versions": artifact_hashes.get("event_versions"),
                "event_edges": artifact_hashes.get("event_edges"),
            },
        },
    )
    validate_registration_lifecycle_bundle(bundle)
    payload = (
        json.dumps(bundle, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    _atomic_write(payload, output_path)
    if output_path.read_bytes() != payload:
        raise ValueError("registration lifecycle artifact changed during promotion")
    return {
        "status": bundle["coverage"]["state"],
        "generation_id": bundle["generation_id"],
        "as_of": bundle["as_of"],
        "lifecycles": bundle["coverage"]["lifecycle_count"],
        "timeline_events": bundle["coverage"]["timeline_event_count"],
        "deferred": bundle["coverage"]["deferred_count"],
        "output_path": str(output_path),
        "byte_length": len(payload),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--generated-at", default=None)
    args = parser.parse_args(argv)
    summary = compile_from_disk(
        root=args.root,
        output_path=args.output_path,
        as_of=args.as_of,
        generated_at=args.generated_at,
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

