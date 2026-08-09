"""Build the display-only ``inflation_intelligence.v1`` state artifact.

Usage:
    python -m scripts.build_inflation_intelligence
    python -m scripts.build_inflation_intelligence --root /path/to/repo --as-of 2026-08-08

Missing FRED or Release Radar inputs are fail-open: the builder still emits a
valid partial artifact with explicit gaps.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.inflation_intelligence import write_inflation_intelligence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None, help="Repository root")
    parser.add_argument("--as-of", default=None, help="Optional YYYY-MM-DD state date")
    parser.add_argument("--radar-latest", type=Path, default=None)
    parser.add_argument("--forward-ledger", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    payload, target = write_inflation_intelligence(
        args.root,
        output_path=args.output,
        as_of=args.as_of,
        radar_latest_path=args.radar_latest,
        forward_ledger_path=args.forward_ledger,
    )
    print(
        "inflation intelligence: "
        f"asof={payload['asof']} "
        f"next_release={payload['next_release_forecast'].get('release_date')} "
        f"gaps={len(payload['gaps'])} path={target}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
