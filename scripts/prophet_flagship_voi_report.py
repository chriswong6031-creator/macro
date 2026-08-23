#!/usr/bin/env python3
"""Emit the MAS-123 Cell-G flagship VOI report to stdout only.

This CLI is intentionally incapable of writing an evaluation artifact and intentionally
has no W3 outcome-path argument.  It reads the owner-written W3 status surface first and
projects that gate verbatim.  Current US-board grades are a separate, already-existing
ledger and are rendered DESCRIPTIVE_ONLY.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from engine.prophet_voi import UNAVAILABLE_FIELD, build_report

DEFAULT_W3_STATUS = Path("data/us_prophet_rank/w3/status.json")
DEFAULT_BOARD_LEDGER = Path("data/us_board_ledger/retro_grades.parquet")


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        value = json.load(fh)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only Prophet flagship Value-of-Information report (MAS-123 Cell G)."
    )
    parser.add_argument("--w3-status", type=Path, default=DEFAULT_W3_STATUS)
    parser.add_argument("--board-ledger", type=Path, default=DEFAULT_BOARD_LEDGER)
    parser.add_argument("--horizon", type=int, default=10)
    parser.add_argument("--lane", default="buy")
    parser.add_argument(
        "--no-board",
        action="store_true",
        help="Emit owner W3 status only; do not open the existing US-board descriptive ledger.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _args(argv)
    try:
        w3 = _read_json(ns.w3_status)
    except Exception as exc:  # noqa: BLE001 -- report the refusal, do not invent a gate
        payload = {
            "schema": "prophet.flagship_voi_report/v1",
            "cell": "MAS-123 / Cell G",
            "promotion_authority": False,
            "writes_evaluation_store": False,
            "w3": {
                "state": UNAVAILABLE_FIELD,
                "reason": f"status_unreadable:{type(exc).__name__}",
                "path": str(ns.w3_status),
                "outcome_files_opened": False,
            },
            "promotion": {"authorized": False, "reason": "W3 owner status unavailable"},
        }
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2

    board: pd.DataFrame | None = None
    board_error: str | None = None
    if not ns.no_board:
        try:
            board = pd.read_parquet(ns.board_ledger)
        except Exception as exc:  # noqa: BLE001 -- a missing descriptive source must stay loud
            board_error = f"board_ledger_unreadable:{type(exc).__name__}"

    report = build_report(w3_status=w3, board_frame=board, horizon=ns.horizon, lane=ns.lane)
    if board_error is not None:
        report["us_board"] = {
            "state": UNAVAILABLE_FIELD,
            "reason": board_error,
            "path": str(ns.board_ledger),
            "promotion_authority": False,
        }
    json.dump(report, sys.stdout, indent=2, sort_keys=True, allow_nan=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
