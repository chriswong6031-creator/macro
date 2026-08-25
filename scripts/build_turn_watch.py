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
import json
import logging
import os
import sys
import time
from datetime import timezone
from hashlib import sha256
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))

from engine import us_turn_watch as turn_watch  # noqa: E402
from engine.session_digest import session_window_et  # noqa: E402
from engine.us_candidate_episode import canonical_json  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

#: Hard nightly budget for this desk (§6.9 R8 — "runtime < 10 min in the nightly").
#: Exceeding it is a printed ::warning, never a failure: a slow deck is still a deck.
BUDGET_SECONDS = 600.0


def write_candidate_episode_input(artifact: dict, rows: list[dict], data_root: Path) -> Path:
    """Atomically write the private, uncapped TURN WATCH intake sidecar.

    The public document remains capped at ``site/turn_watch``.  This private Data OS input
    carries the same already-computed rows and never asks the deck to recompute them.
    """
    session = artifact.get("data_session")
    if not isinstance(session, str) or not session:
        raise ValueError("TURN WATCH data_session is required for candidate episode input")
    known_at = session_window_et(session)[1].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    artifact_sha = sha256(canonical_json(artifact).encode("utf-8")).hexdigest()
    document = {
        "schema": "prophet.candidate_episode_input.turn_watch/v1",
        "data_session": session,
        "known_at": known_at,
        "selection_era": artifact.get("selection_era"),
        "anchor_era": artifact.get("anchor_era"),
        "trigger_registry": artifact.get("triggers"),
        "source_artifact_sha256": "sha256:" + artifact_sha,
        "rows": rows,
    }
    document["content_sha256"] = sha256(canonical_json(document).encode("utf-8")).hexdigest()
    out = Path(data_root) / "us_prophet_rank" / "episode_inputs" / "turn_watch" / f"{session}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_name(f".{out.name}.tmp")
    payload = canonical_json(document) + "\n"
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, out)
    return out


def build(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=None,
                    help="deterministic alphabetical universe subset; disclosed in the "
                         "artifact as coverage.universe_limit")
    ap.add_argument("--cap", type=int, default=turn_watch.DECK_CAP)
    args = ap.parse_args(argv)

    t0 = time.time()
    try:
        artifact, rows = turn_watch.compute_deck_with_candidates(
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
        write_candidate_episode_input(artifact, rows, config.data_dir())
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
