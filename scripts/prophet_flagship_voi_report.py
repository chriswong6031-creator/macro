#!/usr/bin/env python3
"""Emit the MAS-123 Cell-G flagship VOI report to stdout only.

The executable is deliberately source-pinned. Operators cannot redirect it to an
arbitrary W3 JSON, QLedger result path, or parquet file. It reads only:

1. canonical ``data/us_prophet_rank/w3/status.json``;
2. canonical ``data/qledger/evidence_clock_start/*.json`` metadata; and
3. canonical ``data/us_board_ledger/retro_grades.parquet`` unless ``--no-board``.

That source pin is part of the outcome-read gate: an immature W3 result file cannot be
smuggled in through a generic CLI path and read before schema rejection. Current board
telemetry remains DESCRIPTIVE_ONLY. This CLI has no writer and grants no authority.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import pandas as pd

from engine.prophet_voi import HOLD_INTEGRITY, MEASURED, UNAVAILABLE_FIELD, build_report

# Absolute repository-root pins are load-bearing. Relative paths would let the caller's
# working directory silently substitute a lookalike data/... tree.
DEFAULT_W3_STATUS = _ROOT / "data/us_prophet_rank/w3/status.json"
DEFAULT_QLEDGER_CLOCK_DIR = _ROOT / "data/qledger/evidence_clock_start"
DEFAULT_BOARD_LEDGER = _ROOT / "data/us_board_ledger/retro_grades.parquet"


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        value = json.load(fh)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def _strict_positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(field)
    return value


def _strict_utc_timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(field) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(field)
    return value


def _strict_git_sha(value: Any) -> str:
    if not isinstance(value, str) or len(value) not in {40, 64}:
        raise ValueError("git_sha")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError("git_sha") from exc
    return value.lower()


def _qledger_clock_inventory() -> dict[str, Any]:
    """Read only canonical evidence-clock metadata; never QLedger claims/grades."""
    root = DEFAULT_QLEDGER_CLOCK_DIR
    if not root.is_dir():
        return {
            "state": UNAVAILABLE_FIELD,
            "path": str(root),
            "registrations": [],
            "reason": "canonical_evidence_clock_directory_missing",
            "outcome_files_opened": False,
        }

    registrations: list[dict[str, Any]] = []
    invalid: list[dict[str, str]] = []
    for path in sorted(root.glob("*.json")):
        try:
            row = _read_json(path)
            claim_family = row.get("claim_family")
            horizon = _strict_positive_int(row.get("declared_horizon_d"), "declared_horizon_d")
            unit = row.get("horizon_unit")
            started = _strict_utc_timestamp(
                row.get("first_prospective_registration_utc"),
                "first_prospective_registration_utc",
            )
            git_sha = _strict_git_sha(row.get("git_sha"))
            if not isinstance(claim_family, str) or not claim_family:
                raise ValueError("claim_family")
            if path.stem != claim_family:
                raise ValueError("filename_claim_family_mismatch")
            if unit not in {"trading_days", "calendar_days"}:
                raise ValueError("horizon_unit")
            registrations.append({
                "claim_family": claim_family,
                "declared_horizon_d": horizon,
                "horizon_unit": unit,
                "first_prospective_registration_utc": started,
                "git_sha": git_sha,
                "source": str(path),
                "authority": "evidence-clock metadata only",
            })
        except Exception as exc:  # noqa: BLE001 -- invalid metadata must fail loud
            invalid.append({"source": str(path), "reason": type(exc).__name__})

    return {
        "state": HOLD_INTEGRITY if invalid else MEASURED,
        "path": str(root),
        "registrations": registrations,
        "registration_count": len(registrations),
        "invalid_records": invalid,
        "outcome_files_opened": False,
        "promotion_authority": False,
    }


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only Prophet flagship Value-of-Information report (MAS-123 Cell G)."
    )
    parser.add_argument("--horizon", type=int, default=10)
    parser.add_argument("--lane", default="buy")
    parser.add_argument(
        "--no-board",
        action="store_true",
        help="Emit metadata-only owner gates/clocks without opening the US-board descriptive ledger.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _args(argv)
    try:
        w3 = _read_json(DEFAULT_W3_STATUS)
    except Exception as exc:  # noqa: BLE001 -- report refusal; never invent a gate
        payload = {
            "schema": "prophet.flagship_voi_report/v1",
            "cell": "MAS-123 / Cell G",
            "promotion_authority": False,
            "writes_evaluation_store": False,
            "w3": {
                "state": UNAVAILABLE_FIELD,
                "reason": f"status_unreadable:{type(exc).__name__}",
                "path": str(DEFAULT_W3_STATUS),
                "outcome_files_opened": False,
            },
            "qledger_evidence_clocks": _qledger_clock_inventory(),
            "promotion": {"authorized": False, "reason": "W3 owner status unavailable"},
        }
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2

    board: pd.DataFrame | None = None
    board_error: str | None = None
    if not ns.no_board:
        try:
            board = pd.read_parquet(DEFAULT_BOARD_LEDGER)
        except Exception as exc:  # noqa: BLE001 -- missing descriptive source stays loud
            board_error = f"board_ledger_unreadable:{type(exc).__name__}"

    report = build_report(w3_status=w3, board_frame=board, horizon=ns.horizon, lane=ns.lane)
    report["qledger_evidence_clocks"] = _qledger_clock_inventory()
    if board_error is not None:
        report["us_board"] = {
            "state": UNAVAILABLE_FIELD,
            "reason": board_error,
            "path": str(DEFAULT_BOARD_LEDGER),
            "promotion_authority": False,
        }
    json.dump(report, sys.stdout, indent=2, sort_keys=True, allow_nan=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
