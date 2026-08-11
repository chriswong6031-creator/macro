"""Read one telemetry-bound Capital Structure generation for PIT projection.

This is the shared, read-only half of the Capital Structure projection writer.
It validates the compiler's telemetry-last commit, exact ledger counts, source
manifest prefix and every event/edge/review row before returning inputs.  It
does not publish a projection, fetch SEC, mutate a pointer or create another
store.  Heavy parquet dependencies remain lazy so private in-process adapters
can be imported without widening the serving process dependency surface.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VerifiedProjectionGeneration:
    """Validated inputs and the telemetry receipt that binds them."""

    events: tuple[dict[str, Any], ...]
    edges: tuple[dict[str, Any], ...]
    reviews: tuple[dict[str, Any], ...]
    telemetry: dict[str, Any]


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unreadable JSON object: {path}") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"JSON root must be an object: {path}")
    return dict(value)


def _validate_review_rows(frame: Any) -> list[dict[str, Any]]:
    from jsonschema import Draft202012Validator, FormatChecker

    from scripts.compile_capital_structure_events import (
        REVIEW_COLUMNS,
        _load_contract,
        dataframe_records,
    )

    if frame.columns.tolist() != REVIEW_COLUMNS:
        raise ValueError(
            "review queue columns must exactly equal "
            f"{REVIEW_COLUMNS}; got {frame.columns.tolist()}"
        )
    rows = dataframe_records(frame)
    validator = Draft202012Validator(
        _load_contract("review"), format_checker=FormatChecker()
    )
    for index, row in enumerate(rows):
        errors = list(validator.iter_errors(row))
        if errors:
            raise ValueError(
                f"review queue row {index} violates its contract: {errors[0].message}"
            )
    return rows


def read_verified_projection_generation(
    root: Path | str,
) -> VerifiedProjectionGeneration:
    """Return the compiler generation only after its owner receipts verify.

    A missing generation is represented by empty ledgers plus explicit
    ``status: missing`` telemetry.  A present but inconsistent generation is an
    integrity failure and raises; callers may not turn tampering into an empty
    issuer result.
    """

    import pandas as pd

    from engine.capital_structure.source_ledger_io import (
        read_source_ledger,
        source_ledger_path,
    )
    from scripts.compile_capital_structure_events import (
        EDGE_COLUMNS,
        _load_contract,
        _load_existing_edges,
        _load_existing_events,
        _validate_committed_generation,
    )

    data_root = Path(root)
    manifests = read_source_ledger(source_ledger_path(data_root))
    telemetry_path = data_root / "telemetry.json"
    telemetry = (
        _read_json_object(telemetry_path)
        if telemetry_path.exists()
        else {
            "status": "missing",
            "as_of": None,
            "generation_id": None,
            "artifact_hashes": {},
            "source_ledger_receipt": None,
            "coverage_claim": None,
            "known_exclusions": [],
        }
    )
    has_generation = _validate_committed_generation(
        data_root, _load_contract("telemetry"), manifests
    )
    if not has_generation:
        return VerifiedProjectionGeneration((), (), (), telemetry)

    events = _load_existing_events(
        pd.read_parquet(data_root / "event_versions.parquet"),
        _load_contract("event"),
    )
    edge_frame = pd.read_parquet(data_root / "event_edges.parquet")
    if edge_frame.columns.tolist() != EDGE_COLUMNS:
        raise ValueError("event edge ledger columns changed before projection")
    edges = _load_existing_edges(edge_frame, _load_contract("edge"))
    reviews = _validate_review_rows(
        pd.read_parquet(data_root / "review_queue.parquet")
    )
    return VerifiedProjectionGeneration(
        tuple(events), tuple(edges), tuple(reviews), telemetry
    )


__all__ = ["VerifiedProjectionGeneration", "read_verified_projection_generation"]
