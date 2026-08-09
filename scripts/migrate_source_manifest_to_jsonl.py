"""Convert a retained parquet source-manifest ledger to canonical JSON Lines.

The parquet form let pyarrow's nested-struct unification rewrite retained rows
(see ``engine/capital_structure/source_ledger_io``).  This migration is a pure
re-encoding: it must preserve every ``manifest_id`` and the ordered-prefix hash
exactly, which is what makes it safe for an immutable, receipt-pinned ledger.
Those invariants are asserted, not assumed -- a mismatch aborts without writing.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.capital_structure.source_identity import (
    source_ledger_prefix_hash,
    validate_manifest_ledger,
)
from engine.capital_structure.source_ledger_io import (
    LEGACY_SOURCE_LEDGER_FILENAME,
    decode_source_ledger,
    encode_source_ledger,
    source_ledger_path,
)


def _data_root() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "capital_structure"


def migrate(root: Path, *, dry_run: bool = False) -> dict[str, object]:
    import pandas as pd

    from scripts.compile_capital_structure_events import dataframe_records

    legacy_path = root / LEGACY_SOURCE_LEDGER_FILENAME
    target_path = source_ledger_path(root)
    if not legacy_path.exists():
        return {"status": "no_legacy_ledger", "path": str(legacy_path)}

    records = dataframe_records(pd.read_parquet(legacy_path))
    validate_manifest_ledger(records)
    before_ids = [str(record["manifest_id"]) for record in records]
    before_prefix = source_ledger_prefix_hash(records)

    body = encode_source_ledger(records)
    round_tripped = decode_source_ledger(body, label=str(target_path))
    validate_manifest_ledger(round_tripped)
    after_ids = [str(record["manifest_id"]) for record in round_tripped]
    after_prefix = source_ledger_prefix_hash(round_tripped)

    if after_ids != before_ids:
        raise SystemExit("migration aborted: manifest IDs are not preserved")
    if after_prefix != before_prefix:
        raise SystemExit("migration aborted: ordered-prefix hash is not preserved")
    if round_tripped != records:
        raise SystemExit("migration aborted: records are not byte-identical")

    if not dry_run:
        target_path.write_bytes(body)
    return {
        "status": "migrated" if not dry_run else "dry_run",
        "record_count": len(records),
        "prefix_sha256": before_prefix,
        "target": str(target_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = migrate(args.root or _data_root(), dry_run=args.dry_run)
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
