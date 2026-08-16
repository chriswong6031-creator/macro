"""Fail closed when Capital Structure selected filings without durable evidence.

Reads the collector ingestion_run receipt, retrieval attempts, source ledger,
and compiler telemetry. Writes data/capital_structure/health.json. Exits 1
when filings were selected but zero durable verified evidence progressed.

Usage:
    python -m scripts.check_capital_structure_health
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.capital_structure.ingestion_health import (  # noqa: E402
    HEALTH_FILENAME,
    evaluate_health,
    health_exit_code,
    write_health,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gate Capital Structure ingestion on durable evidence progress",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="capital_structure data directory (default: lib.config data_dir)",
    )
    args = parser.parse_args(argv)
    if args.root is not None:
        root = args.root
    else:
        from lib import config

        root = config.data_dir() / "capital_structure"
    record = evaluate_health(root)
    write_health(record, root / HEALTH_FILENAME)
    code = health_exit_code(record)
    title = "capital-structure-ingestion-health"
    reason = record.get("verdict_reason") or record.get("verdict")
    counters = record.get("counters") or {}
    freshness = (
        f"compiler_generated_at={record.get('compiler_generated_at')} "
        f"latest_source_retrieved_at={record.get('latest_source_retrieved_at')}"
    )
    summary = (
        f"verdict={record.get('verdict')} selected={counters.get('selected')} "
        f"retrieved={counters.get('retrieved')} "
        f"verified_retained={counters.get('verified_retained_sources')} "
        f"manifested={counters.get('manifested_sources')} "
        f"compiled_events={counters.get('compiled_events')} "
        f"storage_deferred={counters.get('storage_deferred')} "
        f"parked={counters.get('parked')} {freshness} {reason}"
    )
    if code:
        print(f"::error title={title}::{summary}", flush=True)
    else:
        kind = "notice" if record.get("verdict") == "ok" else "warning"
        print(f"::{kind} title={title}::{summary}", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
