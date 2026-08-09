#!/usr/bin/env python3
"""build_turn_watch.py — nightly builder for the TURN WATCH desk (ANTICIPATION §6.9 R8).

Writes:
  site/turn_watch/turn_watch.json  — the early-surfacing deck + its whole disclosure block

  NOT site/prophet/ — that root is exclusive Prophet publisher authority and the nightly
  engine job restores it from HEAD before staging, so a deck written there is reverted on a
  SUCCESSFUL night too. This desk owns its own site root; see engine.us_turn_watch
  .write_artifact.

Reads (all committed, no network, no data/ mutations):
  data/yahoo/*.parquet                     the graded deck universe + the SPY benchmark
  data/baskets/membership.json             group names (EN/ZH) and member lists
  site/basketdata/us_basket_turn.json      the group lifecycle states (that organ's artifact)

Spec: research/PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md §6.9 R8.
Schema + the whole trigger/scoring definition: engine/us_turn_watch.py.

DISPLAY TIER, ZERO SCORED AUTHORITY. This builder writes one artifact and advances NO
ledger — the nightly is the sole ledger advancer and this desk keeps no ledger of its own.
Nothing it emits ranks, gates or sizes a graded position.

Never-raise contract: a missing input degrades the deck (fewer rows, printed nulls), it
never fails the nightly. The process exit code is 0 unless the artifact could not be
written at all.

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
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine import us_turn_watch as turn_watch  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

#: Hard nightly budget for this desk (§6.9 R8 — "runtime < 10 min in the nightly").
#: Exceeding it is a printed ::warning, never a failure: a slow deck is still a deck.
BUDGET_SECONDS = 600.0


def build(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=None,
                    help="deterministic alphabetical universe subset; disclosed in the "
                         "artifact as coverage.universe_limit")
    ap.add_argument("--cap", type=int, default=turn_watch.DECK_CAP)
    args = ap.parse_args(argv)

    t0 = time.time()
    try:
        artifact = turn_watch.compute_deck(
            config.data_dir(), config.site_dir(),
            universe_limit=args.limit, cap=args.cap,
        )
    except Exception as e:  # noqa: BLE001 — the deck never fails the nightly
        print(f"::warning title=turn-watch::deck build failed ({e}) "
              f"— site/turn_watch/turn_watch.json NOT refreshed this run", flush=True)
        log.warning("build_turn_watch: compute_deck failed: %s", e, exc_info=True)
        return 0

    try:
        out = turn_watch.write_artifact(artifact, config.site_dir())
    except Exception as e:  # noqa: BLE001
        print(f"::error title=turn-watch::could not write the deck artifact ({e})",
              flush=True)
        log.error("build_turn_watch: write failed: %s", e, exc_info=True)
        return 1

    cov = artifact["coverage"]
    elapsed = round(time.time() - t0, 2)
    if elapsed > BUDGET_SECONDS:
        print(f"::warning title=turn-watch-budget::build took {elapsed}s over the "
              f"{BUDGET_SECONDS}s nightly budget ({cov['graded']} graded names) "
              f"— use --limit for a deterministic subset", flush=True)

    # An EMPTY deck is a real state (nothing triggered), but an empty deck on a universe
    # that did not load is a data failure wearing the same clothes. Say which.
    if cov["graded"] == 0:
        print("::warning title=turn-watch::0 names graded — the price store did not load, "
              "so the empty deck is a data gap, not a quiet tape", flush=True)
    elif cov["triggered"] == 0:
        log.info("build_turn_watch: 0 of %d graded names triggered — quiet tape",
                 cov["graded"])

    log.info(
        "build_turn_watch: wrote %s — deck %d/%d triggered of %d graded "
        "(beyond cap %d), lanes %s, %.1fs",
        out, cov["deck"], cov["triggered"], cov["graded"], cov["beyond_cap"],
        cov["deck_by_trigger"], elapsed,
    )
    return 0


if __name__ == "__main__":
    rc = build()
    from lib.procutil import hard_exit  # noqa: E402  # Arrow shutdown-hang law

    hard_exit(rc)
