#!/usr/bin/env python3
"""Chrome Native Messaging receiver for observe-only MomoEdge evidence."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from engine.options_momoedge_browser_adapter import (
    ACK_SCHEMA,
    ObservationConflict,
    PRIVATE_ROOT_DEFAULT,
    persist_observation,
    read_native_frame,
    write_native_frame,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, default=PRIVATE_ROOT_DEFAULT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = read_native_frame(sys.stdin.buffer)
        response = persist_observation(payload, args.private_root)
    except ObservationConflict:
        response = {
            "schema": ACK_SCHEMA,
            "accepted": False,
            "created": False,
            "disposition": "unavailable",
            "reason": "slot_conflict",
            "journal_sha256": None,
            "raw_sha256": None,
            "coverage_eligible": False,
        }
    # The native protocol must always fail closed with one bounded frame. Do
    # not leak exception text or a payload-derived stack to stderr.
    except Exception:
        response = {
            "schema": ACK_SCHEMA,
            "accepted": False,
            "created": False,
            "disposition": "unavailable",
            "reason": "receiver_rejected",
            "journal_sha256": None,
            "raw_sha256": None,
            "coverage_eligible": False,
        }
    write_native_frame(sys.stdout.buffer, response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
