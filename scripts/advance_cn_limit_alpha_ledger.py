#!/usr/bin/env python3
"""Advance the context-only A-share limit-alpha forward ledger.

The workflow is intentionally fail-soft around this command; this command is
fail-closed.  Any lane, receipt, calendar, source, or immutability violation
returns non-zero without planning new evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine.cn_limit_alpha_ledger import (
    DEFAULT_CALENDAR_PATH,
    DEFAULT_LEDGER_ROOT,
    DEFAULT_RAW_DIR,
    DEFAULT_RECEIPT_PATH,
    DEFAULT_SEED_PATH,
    DEFAULT_ST_PATH,
    advance_forward_ledger,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap and advance the Asia-only CN limit-alpha Parquet ledger."
    )
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT_PATH)
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED_PATH)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--st-snapshot", type=Path, default=DEFAULT_ST_PATH)
    parser.add_argument("--calendar", type=Path, default=DEFAULT_CALENDAR_PATH)
    parser.add_argument("--ledger-root", type=Path, default=DEFAULT_LEDGER_ROOT)
    parser.add_argument(
        "--bootstrap-only",
        action="store_true",
        help="Migrate only the tracked honest seed; do not discover/score/grade a live session.",
    )
    parser.add_argument("--minimum-support-names", type=int, default=50)
    parser.add_argument("--support-ratio", type=float, default=0.98)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    receipt = advance_forward_ledger(
        receipt_path=args.receipt,
        seed_path=args.seed,
        raw_dir=args.raw_dir,
        st_path=args.st_snapshot,
        calendar_path=args.calendar,
        ledger_root=args.ledger_root,
        bootstrap_only=args.bootstrap_only,
        minimum_support_names=args.minimum_support_names,
        support_ratio=args.support_ratio,
    )
    print(json.dumps(receipt.as_dict(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
