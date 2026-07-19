#!/usr/bin/env python3
"""Build the Stage Analysis (SGA) context feed + forward ledger.

Thin CLI over engine.stage_analysis. Runs in the daily.yml parallel band,
off the render-critical path (masterplan W1).

Exit 0 even on partial failure (logs ::warning::); exit 1 only on a total
failure (the engine could not produce a contract at all).

Usage:
    python -m scripts.build_stage_analysis [--root DATA_ROOT] [--asof YYYY-MM-DD]
                                           [--max-workers N] [--fixture PATH]

--fixture PATH: skip the universe fan-out and load a pre-built stage_context.v1
    JSON (used by tests / dry runs); the forward ledger is still appended from it.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Make the repo root importable when run as a bare script.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine import stage_analysis  # noqa: E402

log = logging.getLogger("build_stage_analysis")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the Stage Analysis context feed.")
    ap.add_argument("--root", default=None,
                    help="Data root override (defaults to repo data/).")
    ap.add_argument("--asof", default=None,
                    help="As-of date YYYY-MM-DD (defaults to today UTC).")
    ap.add_argument("--max-workers", type=int, default=None,
                    help="Process-pool size (capped at 4 by the engine).")
    ap.add_argument("--fixture", default=None,
                    help="Load a pre-built stage_context.v1 JSON instead of "
                         "running the universe fan-out (tests / dry runs).")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    root = Path(args.root) if args.root else None

    try:
        if args.fixture:
            fx = Path(args.fixture)
            contract = json.loads(fx.read_text())
            log.info("loaded fixture contract from %s (asof=%s)",
                     fx, contract.get("asof"))
        else:
            contract = stage_analysis.build_context_feed(
                root=root, asof=args.asof, max_workers=args.max_workers)
    except Exception as e:  # noqa: BLE001 — total failure
        log.error("::error:: stage_analysis: context feed failed entirely (%s)", e)
        return 1

    if not contract or contract.get("schema") != "stage_context.v1":
        log.error("::error:: stage_analysis: no valid contract produced")
        return 1

    counts = contract.get("counts") or {}
    log.info("stage_context.v1 asof=%s total=%s stage2=%s fresh=%s changes=%s",
             contract.get("asof"), counts.get("total"),
             counts.get("stage2"), counts.get("stage2_fresh"),
             (contract.get("changes") or {}).get("n"))

    # Forward ledger (SGA-R7) — fail-open, never fatal.
    try:
        n_led = stage_analysis.append_forward_ledger(contract, root=root)
        log.info("forward ledger: appended %d fresh-Stage-2 row(s)", n_led)
    except Exception as e:  # noqa: BLE001
        log.warning("::warning:: forward-ledger append failed (%s)", e)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
