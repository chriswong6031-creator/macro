#!/usr/bin/env python3
"""CLI: validate MOR-1 route-semantic evidence against the frozen 32-cell matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.market_reference_route_evidence import validate_manifest_route_matrix

DEFAULT_MANIFEST = Path("mockups/evidence/market_reference_mor1/manifest.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="path to mastermind.p0_evidence.v2 manifest (repo-relative or absolute)",
    )
    args = parser.parse_args(argv)
    path = args.manifest
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        print(f"ERROR: manifest not found: {path}", file=sys.stderr)
        return 2
    manifest = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_manifest_route_matrix(manifest)
    if errors:
        print(f"MOR-1 route evidence RED ({len(errors)} defect(s)) — {path}")
        for err in errors:
            print(f"  - {err}")
        return 1
    pages = manifest.get("pages") or []
    captured = sum(
        1
        for p in pages
        for s in (p.get("states") or [])
        if isinstance(s, dict) and s.get("captured")
    )
    print(f"MOR-1 route evidence GREEN — {len(pages)} route pages, {captured} captured cells — {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
