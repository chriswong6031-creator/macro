"""scripts.close_pass_mirror — R2 → the VPS live plane, and nothing else.

The evening board is COMPUTED on the mac pool (the price store lives there) and
READ by a browser from the VPS, so something has to carry it across. This is
that something, and it is deliberately the dumbest program in the lane.

It lands the board in two places, for two different readers:

  live/us_board_provisional.json   the FULL board — what the freshness sentinel
                                   measures the 18:30 ET SLA against and what a
                                   later card renderer will read.
  live/prophet_live.json           the ``board_state`` KEY only — the small view
                                   the W-L1b surface consumes. It rides the
                                   artifact the live strip already fetches so
                                   the page keeps one artifact, one poll, one
                                   client, instead of a second hydration path.

IT NEVER COMPUTES. No ranking, no re-admission, no reordering — the board it
serves is the board the pass published, and ``board_state`` is a projection of
that same payload (engine.close_pass.board.board_state), never a second opinion.

TWO WRITERS ON prophet_live.json, AND WHY THAT IS SAFE. The Prophet Live
evaluator owns that file and rewrites it whole every five minutes, so this lane
read-modify-writes a key into someone else's artifact. Three things make that
sound rather than lucky:
  * ``annotate_live_strip`` COMPARE-AND-SWAPS: it re-reads the file immediately
    before writing and skips the write if the bytes moved, so a lost race costs
    this lane its own key for one tick instead of costing the evaluator its
    whole document. The disjoint-windows argument this lane originally shipped
    on (evaluator ends 16:15 ET, board publishes ~16:25 ET) is TRUE IN THE
    ORDINARY CASE AND NOT LOAD-BEARING — measured queue waits reach 71 minutes,
    which is enough to push this pass into a period the evaluator owns;
  * every remaining failure — absent file, unparseable file, skipped swap — ends
    with no key, and a missing key means the surface paints NOTHING. The failure
    direction is dark, never wrong;
  * the payload carries ``valid_until``, and the client refuses to paint past
    it, so a key that survives longer than it should expires itself.
This lane NEVER creates prophet_live.json and never writes any other key in it:
if the evaluator has not produced the file, there is nothing here to annotate.

Writes no ``data/`` path, runs no git command, creates no directory (G0.2).

Usage:
  python -m scripts.close_pass_mirror
  python -m scripts.close_pass_mirror --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.close_pass import board as CB  # noqa: E402
from engine.prophet_live import r2io  # noqa: E402
from scripts.close_pass_publish import (  # noqa: E402
    BOARD_KEY, SERVED_PATH, publish_served,
)

#: The artifact the W-L1b surface polls. Owned by the Prophet Live evaluator —
#: this lane only ever adds one key to it, and only if it already exists.
PLV_SERVED_PATH = "/var/lib/macro-live/public/live/prophet_live.json"
#: The one key this lane may write there. Named as a constant so the "and
#: nothing else" rule is checkable rather than merely stated.
STATE_KEY = "board_state"

_TAG = "close-pass"


def _read_doc(path: Path) -> tuple[dict | None, str | None]:
    """``(doc, fingerprint)`` — the parsed object and a digest of its BYTES.

    The fingerprint is taken over the raw bytes rather than the parsed object
    because it has to answer "did this file change", and two different byte
    strings can parse to equal dicts (key order, spacing, float formatting). A
    digest over the bytes is the honest question; a digest over the parse is a
    weaker one that would call a real rewrite "unchanged".
    """
    try:
        raw = path.read_bytes()
        doc = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None, None
    if not isinstance(doc, dict):
        return None, None
    return doc, hashlib.sha256(raw).hexdigest()


def _read_json(path: Path) -> dict | None:
    return _read_doc(path)[0]


def served_as_of(path: Path) -> str | None:
    """The session the currently-served copy describes, or None."""
    return (_read_json(path) or {}).get("as_of")


def annotate_live_strip(path: Path, payload: dict, *, dry_run: bool = False) -> bool:
    """Merge ``board_state`` into the served prophet_live.json. Never creates it.

    Read-modify-write on an artifact another lane owns, guarded by a
    COMPARE-AND-SWAP: the file is re-read immediately before the write and the
    write is SKIPPED if its bytes moved under us.

    WHY THE DISJOINT-WINDOWS ARGUMENT WAS NOT ENOUGH. This lane was accepted on
    the reasoning that the evaluator's window ends 16:15 ET and the board
    publishes ~16:25 ET, so the two never write in the same period. The lane's
    own measurement undercuts it: observed queue waits of up to 71 minutes move
    this pass an hour or more past its nominal slot, straight into a period the
    evaluator owns. Without the swap the loser of that race does not lose its
    own key — it clobbers the WINNER'S whole document with a stale copy plus one
    key, and the evaluator's fresh live data is gone until its next pass.

    The swap narrows the window to (re-read → serialise → rename); it does not
    close it, because a rename cannot be conditioned on a digest without a lock
    the evaluator does not take. That residual is stated, not papered over. It
    is also the acceptable direction: a skipped write costs one tick, which is
    the failure this lane was already designed to absorb.

    Every failure direction stays DARK — an absent file, an unparseable one, a
    lost race and a skipped swap all end with no key, and no key means the
    surface paints nothing rather than something wrong. Idempotent as before:
    an already-correct key writes nothing at all.
    """
    doc, seen = _read_doc(path)
    if doc is None:
        # Before the first evaluator pass of the day, or on a host with no live
        # plane. Creating the file would hand the surface a prophet artifact
        # with no prophet data in it.
        return False
    state = CB.board_state(payload)
    if doc.get(STATE_KEY) == state:
        return False                          # already annotated — the common tick
    if dry_run:
        print(f"dry-run: would annotate {path} with {state['rel']} "
              f"({len(state['board']['tickers'])} tickers)", flush=True)
        return False
    # COMPARE-AND-SWAP. Re-read LAST, so the evaluator's rewrite is detected
    # here rather than overwritten below.
    if _read_doc(path)[1] != seen:
        print(f"::notice title={_TAG}::{path.name} was rewritten while this "
              "pass was building its key — skipping rather than clobbering the "
              "newer document (the next tick re-annotates)", flush=True)
        return False
    doc[STATE_KEY] = state
    return publish_served(path, doc)


def run(*, served: str = SERVED_PATH, plv: str = PLV_SERVED_PATH,
        dry_run: bool = False, fetch=None) -> int:
    # Resolved at CALL time: a default of r2io.get_json binds the function object
    # at import and makes the boundary unpatchable, so a test meaning to stub R2
    # would silently reach the real bucket instead.
    fetch = fetch or r2io.get_json
    path = Path(served)
    payload = fetch(BOARD_KEY)
    if not payload or not payload.get("as_of"):
        # Absent is the ORDINARY state before the evening pass runs, so this is a
        # notice rather than a warning — an alarm that fires ~40 times a day
        # trains the operator to ignore the channel.
        print(f"::notice title={_TAG}::no provisional board on the plane yet",
              flush=True)
        return 0

    if served_as_of(path) != payload["as_of"]:
        if dry_run:
            print(f"dry-run: would mirror {payload['as_of']}", flush=True)
        else:
            publish_served(path, payload)

    # Independently of the full-board copy: the surface reads only this key, and
    # a mirror that skipped it because the big file was already current would
    # leave the page unstamped after any single-sided failure.
    if plv:
        annotate_live_strip(Path(plv), payload, dry_run=dry_run)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mirror the provisional board to the live plane")
    ap.add_argument("--served-path", default=SERVED_PATH)
    ap.add_argument("--live-strip-path", default=PLV_SERVED_PATH,
                    help="'' to mirror the board without annotating the strip")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    return run(served=args.served_path, plv=args.live_strip_path,
               dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
