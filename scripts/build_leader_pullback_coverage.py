#!/usr/bin/env python3
"""build_leader_pullback_coverage.py — nightly publisher for the LEADER-PULLBACK organ.

Writes:
  site/anticipationdata/us_leader_pullback.json — per-name organ state for the US graded
  universe, the artifact `engine.us_early_turn.load_leader_pullback_states` reads.

  NOT site/prophet/ — that root is exclusive Prophet publisher authority and the nightly
  engine job restores it from HEAD before staging, so an artifact written there is
  reverted on a SUCCESSFUL night too.

Reads (all committed, no network, no data/ mutations):
  data/yahoo/*.parquet   the graded universe + the SPY benchmark

MUST RUN BEFORE scripts.build_prophet. The EARLY-TURN starter intake (§6.9 R3) resolves
its leader-pullback licence from this file at origination time; a publisher scheduled
after the board would license tonight's plans off yesterday's coverage for no reason.

DISPLAY TIER, ZERO AUTHORITY. Advances NO ledger and writes no data/ path — the nightly
is the sole advancer of forward ledgers and this is a per-run site artifact builder.

Never-raise contract: a degraded input publishes fewer names with their reasons printed;
a RUN-WIDE data failure publishes nothing and leaves the previous artifact in place
(writing a board of nulls would delete real coverage and make a broken price store
indistinguishable from a quiet tape). The exit code is 0 unless the write itself failed.

Spec: research/PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md §6.9 R3/R4.
Schema and the whole construction: engine/us_leader_pullback_coverage.py.

Ends with lib.procutil.hard_exit() — the Arrow shutdown-hang law for parquet-reading
one-shots.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))

from engine import us_leader_pullback_coverage as coverage  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

#: Hard nightly budget. Exceeding it is a printed ::warning, never a failure — the sibling
#: TURN WATCH desk measured ~135s over 702 graded names running the same organ, and this
#: publisher runs it over the same universe.
BUDGET_SECONDS = 600.0


def build(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=None,
                    help="deterministic alphabetical universe subset; disclosed in the "
                         "artifact as coverage.universe_limit")
    args = ap.parse_args(argv)

    t0 = time.time()
    try:
        out, artifact = coverage.run(
            config.data_dir(), config.site_dir(), universe_limit=args.limit)
    except Exception as e:  # noqa: BLE001 — the publisher never fails the nightly
        print(f"::warning title=leader-pullback-coverage::publish failed ({e}) "
              f"— site/anticipationdata/us_leader_pullback.json NOT refreshed this run; "
              f"the EARLY-TURN leader half reads the previous artifact", flush=True)
        log.warning("build_leader_pullback_coverage: run failed: %s", e, exc_info=True)
        return 0

    cov = artifact["coverage"]
    elapsed = round(time.time() - t0, 2)
    if elapsed > BUDGET_SECONDS:
        print(f"::warning title=leader-pullback-coverage-budget::build took {elapsed}s "
              f"over the {BUDGET_SECONDS}s nightly budget ({cov['graded']} graded names) "
              f"— use --limit for a deterministic subset", flush=True)

    if out is None:
        # compute_coverage already printed the run-wide ::warning with its own counts.
        log.warning("build_leader_pullback_coverage: nothing published "
                    "(universe=%d graded=%d cross_section=%d)",
                    cov["universe"], cov["graded"], cov["cross_section_names"])
        return 0

    log.info(
        "build_leader_pullback_coverage: wrote %s — %d states over %d graded of %d "
        "universe (cross-section %d, short history %d), states %s, nulls %s, %.1fs",
        out, cov["states_published"], cov["graded"], cov["universe"],
        cov["cross_section_names"], cov["skipped_short_history"],
        cov["state_counts"], cov["null_counts"], elapsed,
    )
    return 0


if __name__ == "__main__":
    rc = build()
    from lib.procutil import hard_exit  # noqa: E402  # Arrow shutdown-hang law

    hard_exit(rc)
