"""Nightly build step: basket_turn.v1 cohort claims + tape_disagreement.v1 (FTR W9).

  python -m scripts.build_basket_turn_grading

Runs two grading families for the FTR fast-turn program:

  1. basket_turn.v1 qledger cohort claims
     Reads data/basket_turn/ledger.jsonl (written by engine/basket_turn_watch.py).
     Groups IGNITION-day baskets into cohort-day claims.
     Registers one qledger claim per cohort (equal-weight basket vs SPY, 21d horizon).
     Gated on COLLECT_LANE=nightly.

  2. tape_disagreement.v1 survival ledger
     Detects disagreement events: basket IGNITION while slow reco NOT IN
     {enter, accumulate}.
     Appends to data/basket_turn/disagreement_ledger.jsonl (keep-first per
     basket+date), updates outcome columns as windows mature.
     Gated on COLLECT_LANE=nightly.

Called from the nightly engine job, after build_basket_turn_watch (the source
ledger must exist).  Non-fatal: a build failure here never breaks the main
site render.  Exits 0 always (emits ::warning:: on error).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import basket_turn_cohort as btc
from engine import tape_disagreement as td
from lib import config

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_basket_turn_grading")


def main() -> int:
    root = config.ROOT
    data_root = config.data_dir()

    # ── 1. basket_turn.v1 cohort claims ───────────────────────────────────────
    log.info("=== basket_turn.v1 cohort claims ===")
    cohort_summary = btc.nightly_run(data_root=data_root, root=root)

    if not cohort_summary.get("ok"):
        log.warning("basket_turn_cohort.nightly_run reported error: %s",
                    cohort_summary.get("error"))
        # Non-fatal — continue to tape_disagreement
    else:
        if cohort_summary.get("gate_skipped"):
            log.info("basket_turn_cohort: COLLECT_LANE gate not set — "
                     "skipped ledger writes (nightly-only)")
        else:
            log.info(
                "basket_turn_cohort: %d ledger rows → %d cohort(s) → "
                "%d qledger claim(s) registered",
                cohort_summary.get("n_ledger_rows", 0),
                cohort_summary.get("n_cohorts", 0),
                cohort_summary.get("n_claims_registered", 0),
            )

    # ── 2. tape_disagreement.v1 survival ledger ───────────────────────────────
    log.info("=== tape_disagreement.v1 survival ledger ===")
    disagree_summary = td.nightly_run(data_root=data_root, root=root)

    if not disagree_summary.get("ok"):
        log.warning("tape_disagreement.nightly_run reported error: %s",
                    disagree_summary.get("error"))
    else:
        if disagree_summary.get("gate_skipped"):
            log.info("tape_disagreement: COLLECT_LANE gate not set — "
                     "skipped ledger writes (nightly-only)")
        else:
            log.info(
                "tape_disagreement: %d new events, %d outcome updates, "
                "%d total rows",
                disagree_summary.get("n_new_events", 0),
                disagree_summary.get("n_outcome_updates", 0),
                disagree_summary.get("n_total_rows", 0),
            )

    # Always exit 0 (non-fatal contract)
    return 0


if __name__ == "__main__":
    sys.exit(main())
