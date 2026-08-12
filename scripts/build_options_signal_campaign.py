"""Nightly entry point for canonical campaign revisions and anchored outcomes."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.options_signal_campaign import CampaignContractError, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Accrue exact-contract campaign revisions and research-only outcomes"
    )
    parser.add_argument(
        "--root-dir",
        default=None,
        help="repository root override for isolated validation",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and derive without writing",
    )
    args = parser.parse_args(argv)
    try:
        summary = run(
            root_dir=Path(args.root_dir) if args.root_dir else None,
            dry_run=bool(args.dry_run),
        )
    except (CampaignContractError, OSError, ValueError) as exc:
        print(
            f"::error title=options-signal-campaign::{type(exc).__name__}: {exc}",
            flush=True,
        )
        return 1
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
