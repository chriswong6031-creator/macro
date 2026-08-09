"""Run the armed Prophet pick-autopsy accrual lane.

The wrapper exists so daily.yml has one auditable entry point.  It prints only
status/counts; per-pick content remains in the committed autopsy artifacts.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.metabolism.standout_auditor import run_pick_autopsies  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Accrue Prophet per-pick autopsies")
    parser.add_argument("--market", choices=("us", "cn"), default="us")
    parser.add_argument("--cycle-id", default=None)
    args = parser.parse_args()
    cycle_id = args.cycle_id or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    result = run_pick_autopsies(args.market, cycle_id)
    print(
        "prophet_pick_autopsies: market={market} status={status} written={written}".format(
            market=args.market,
            status=result.get("status", "unknown"),
            written=len(result.get("written") or []),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
