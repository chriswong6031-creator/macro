#!/usr/bin/env python3
"""CLI: validate MOR-1 route-semantic evidence against the frozen 32-cell matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Direct invocation bootstrap: `python scripts/check_market_reference_route_evidence.py`
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

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
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=None,
        help="directory containing content-addressed PNGs (defaults to manifest parent)",
    )
    args = parser.parse_args(argv)
    path = args.manifest
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        print(f"ERROR: manifest not found: {path}", file=sys.stderr)
        return 2
    evidence_dir = args.evidence_dir
    if evidence_dir is None:
        evidence_dir = path.parent
    elif not evidence_dir.is_absolute():
        evidence_dir = Path.cwd() / evidence_dir
    manifest = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_manifest_route_matrix(manifest, evidence_dir=evidence_dir)
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
    print(
        f"MOR-1 route evidence GREEN — {len(pages)} route pages, "
        f"{captured} captured cells — {path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
