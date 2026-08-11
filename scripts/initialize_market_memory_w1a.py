#!/usr/bin/env python3
"""Initialize or authenticate the public W1A generation spine."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.neuralweb import market_memory_pit as pit


def initialize_w1a_store(root: str | Path) -> dict[str, Any]:
    """Create or authenticate W1A metadata without creating a capture.

    The underlying owner may finish only its deterministic empty-init prefix
    after an interrupted first attempt. Capture-bearing partial state, tamper,
    crash orphans outside published ancestry, and missing ancestry still fail.
    """

    unresolved = Path(root).expanduser()
    if unresolved.is_symlink():
        raise pit.MarketMemoryStoreError("Market Memory PIT store root is a symlink")
    store = pit.validate_store_root(unresolved)
    try:
        pit._mkdir_durable(store)
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(store, flags)
    except OSError as exc:
        raise pit.MarketMemoryStoreError(
            "W1A store root cannot be initialized safely"
        ) from exc
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        pit._initialize_or_load_store(store)
    except OSError as exc:
        raise pit.MarketMemoryStoreError(
            "W1A store metadata cannot be initialized safely"
        ) from exc
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)

    snapshot = pit.FileAsKnownAtReader(store).read_pinned_generation()
    return {
        "schema": pit._STORE_MANIFEST_SCHEMA,
        "profile": snapshot.profile,
        "store_id": snapshot.store_id,
        "generation_id": snapshot.generation_id,
        "generation_sha256": snapshot.generation_sha256,
        "capture_count": len(snapshot.captures),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create or authenticate W1A manifest/genesis/HEAD metadata without "
            "capturing or materializing a context."
        )
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=_ROOT,
        help="reviewed repository root used only to resolve the production default",
    )
    parser.add_argument(
        "--store",
        type=Path,
        default=None,
        help="W1A store root override (deployment/tests only)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    store = args.store or pit.default_store_root(args.repository_root)
    try:
        result = initialize_w1a_store(store)
    except pit.MarketMemoryPITError as exc:
        print(f"W1A initialization rejected: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, allow_nan=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
