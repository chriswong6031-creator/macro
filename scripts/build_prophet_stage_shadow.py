#!/usr/bin/env python3
"""scripts/build_prophet_stage_shadow.py — the live-Prophet × Stage forward-shadow.

Thin CLI over ``engine.prophet_stage_shadow``. Off the render-critical path (a
forward-accrual ledger, not a render artifact). Each run:

  1. tag_entries()   — UPSERT a PIT stage-at-entry + last-EC tag for every Prophet
                       entry (active + closed), keyed by plan id. Idempotent: an
                       already-tagged id is never re-tagged. Runs in ANY lane.
  2. grade_matured() — advance grades for matured entries. NIGHTLY IS THE SOLE
                       ADVANCER (COLLECT_LANE=nightly); a non-nightly run tags but
                       does NOT advance grades.
  3. summarize()     — emit data/prophet_stage_shadow/summary.json (display-only,
                       is_context_only). Nulls printed; no 'validated'; no trading verbs.

This is the DEFINITIVE on-Prophet test the pre-registered backtest §6 left open. It
NEVER gates, ranks, or alters any Prophet decision — display / shadow tier only.

data/prophet_stage_shadow/ledger.jsonl is a FORWARD LEDGER (gitignored; nightly-only
advancer). summary.json is a small display artifact (committed).

Usage:
    python -m scripts.build_prophet_stage_shadow [--root DATA_ROOT] [--asof YYYY-MM-DD]
        [--site-root PATH] [--ec-path PATH]

Exit 0 on partial failure (a forward-accrual job must never abort the nightly deploy).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine import prophet_stage_shadow as pss  # noqa: E402
from engine.ledger_lane import nightly_advance_enabled  # noqa: E402

log = logging.getLogger("build_prophet_stage_shadow")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Build the live-Prophet × Stage forward-shadow (tag + grade + summarize).")
    ap.add_argument("--root", default=None, help="Data root (defaults to repo data/).")
    ap.add_argument("--asof", default=None, help="ISO asof date (defaults to today UTC).")
    ap.add_argument("--site-root", default=None, help="Site root (defaults to repo site/).")
    ap.add_argument("--ec-path", default=None, help="Override earnings_calls parquet path.")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    try:
        # 1. tag (any lane) — idempotent, PIT-fixed.
        tag = pss.tag_entries(root=args.root, site_root=args.site_root,
                              ec_path=args.ec_path, asof=args.asof)
        log.info("prophet_stage_shadow: tagged — %s", tag)
    except Exception as e:  # noqa: BLE001
        log.warning("prophet_stage_shadow: tag_entries failed (non-fatal): %s", e)
        tag = {}

    try:
        # 2. grade (nightly-only advancer; no-op otherwise).
        grade = pss.grade_matured(root=args.root, asof=args.asof)
        if grade.get("gate_open"):
            log.info("prophet_stage_shadow: graded — %s", grade)
        else:
            log.info("prophet_stage_shadow: grade advance SKIPPED "
                     "(COLLECT_LANE != nightly — nightly is the sole advancer)")
    except Exception as e:  # noqa: BLE001
        log.warning("prophet_stage_shadow: grade_matured failed (non-fatal): %s", e)
        grade = {}

    try:
        # 3. summarize (display-only artifact; nulls printed).
        summary = pss.summarize(root=args.root, asof=args.asof)
        log.info("prophet_stage_shadow: summary — n_entries=%s n_tagged=%s stage2_n=%s",
                 summary.get("n_entries"), summary.get("n_tagged"),
                 summary.get("split", {}).get("stage2", {}).get("n"))
    except Exception as e:  # noqa: BLE001
        log.warning("prophet_stage_shadow: summarize failed (non-fatal): %s", e)

    print("prophet_stage_shadow: forward-accrual only — display/shadow tier; "
          "NEVER gates/ranks/alters Prophet. Nightly is the sole grade advancer "
          f"(gate_open={nightly_advance_enabled()}). " + pss.ACCRUAL_DISCLAIMER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
