"""Compile a supplied immutable SEC Company Facts snapshot into share-count facts.

This command is intentionally not a collector.  It never fetches SEC endpoints
and never consults the legacy fetch-time ``edgar_facts`` cache as a historical
point-in-time source.  An upstream intake lane must first retain exact Company
Facts bytes and pass a closed, hash-bound receipt with durable raw-object and
manifest locators.  Without both inputs the command
prints an explicit unavailable result rather than inventing coverage.

Usage:
  python -m scripts.compile_capital_structure_share_counts \
      --source-json retained-companyfacts.json --receipt-json receipt.json \
      --output observations.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from engine.capital_structure.share_count_truth import (
    ShareCountTruthError,
    compile_share_count_observations,
    source_acquisition_unavailable_result,
)


def _load_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ShareCountTruthError(f"cannot load {label}: {path}") from exc
    if not isinstance(decoded, dict):
        raise ShareCountTruthError(f"{label} must be a JSON object")
    return decoded


def _load_observations(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ShareCountTruthError(f"cannot load existing observations: {path}") from exc
    if not isinstance(decoded, list) or not all(isinstance(row, dict) for row in decoded):
        raise ShareCountTruthError("existing observations must be a JSON array of objects")
    return decoded


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-json", type=Path, help="retained raw Company Facts JSON bytes")
    parser.add_argument("--receipt-json", type=Path, help="hash-bound source receipt JSON")
    parser.add_argument("--existing-observations-json", type=Path, help="immutable prior observation ledger JSON")
    parser.add_argument("--output", type=Path, help="optional result JSON path; stdout when omitted")
    args = parser.parse_args(argv)
    if (args.source_json is None) != (args.receipt_json is None):
        parser.error("--source-json and --receipt-json must be supplied together")
    try:
        if args.source_json is None:
            result = source_acquisition_unavailable_result()
        else:
            receipt = _load_object(args.receipt_json, label="source receipt")
            source_bytes = args.source_json.read_bytes()
            existing = _load_observations(args.existing_observations_json)
            result = compile_share_count_observations(
                source_bytes, receipt, existing_observations=existing,
            )
    except (OSError, ShareCountTruthError) as exc:
        print(_canonical_json({"status": "error", "error": str(exc)}))
        return 2
    rendered = _canonical_json(result)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
