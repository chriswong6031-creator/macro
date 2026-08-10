#!/usr/bin/env python3
"""Capture one exact Market Memory operational packet into the W1A store."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.neuralweb.market_memory_pit import (
    MarketMemoryPITError,
    capture_context,
    default_store_root,
    load_packet_file,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and create-once capture one contemporaneous "
            "market_memory.as_known_at.v1 operational packet."
        )
    )
    parser.add_argument(
        "--packet",
        required=True,
        type=Path,
        help="bounded strict-JSON packet file",
    )
    parser.add_argument(
        "--store",
        type=Path,
        default=None,
        help=(
            "dedicated immutable store root; defaults to the private local "
            "data path in development or /var/lib/macro-market-memory/public "
            "for the /opt/macro production checkout"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    store = args.store or default_store_root(_ROOT)
    try:
        packet = load_packet_file(args.packet)
        stored = capture_context(store, packet)
    except MarketMemoryPITError as exc:
        print(f"capture rejected: {exc}", file=sys.stderr)
        return 2
    receipt = stored.capture_receipt
    print(
        json.dumps(
            {
                "status": "captured",
                "capture_id": receipt["capture_id"],
                "query_id": receipt["query_id"],
                "context_id": receipt["context_id"],
                "packet_sha256": receipt["packet_sha256"],
            },
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
