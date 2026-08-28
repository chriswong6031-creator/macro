#!/usr/bin/env python3
"""Emit one strict, secret-free Provider Capacity snapshot to stdout.

This is a bounded no-write consumer of the Macro-owned projection.  It reads
local Provider Control observations, performs no provider call, persists no
capacity state and returns no credential material.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.provider_capacity import (  # noqa: E402
    ProviderCapacityError,
    build_snapshot,
    canonical_json,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Emit mastermind.provider_capacity.v1 JSON to stdout",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="indent the already-canonical strict document for operator reading",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        document = build_snapshot(repo_root=_ROOT)
        sys.stdout.write(canonical_json(document, pretty=args.pretty))
    except ProviderCapacityError as exc:
        # The exception vocabulary is bounded and contains no source values,
        # paths, stderr or provider response material.
        print(f"provider_capacity refused: {exc}", file=sys.stderr)
        return 2
    except Exception:  # noqa: BLE001 - never expose source/private exception text
        print("provider_capacity refused: INTERNAL_PROJECTION_ERROR", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
