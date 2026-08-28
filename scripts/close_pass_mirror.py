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

THE CALLER USED TO DISCARD ALL OF THAT (fixed alongside the 27-day US Prophet
Live freeze, 2026-08-26). ``run()`` called ``annotate_live_strip`` and threw
away its boolean, so an absent or unparseable target — the exact shape of that
incident, where the served file did not exist at all — produced the SAME
silent ``False`` as the three benign reasons above (already annotated, dry-run,
CAS skip). Three separate instruments stayed green through the whole freeze.
``run()`` now reads ``_annotate_live_strip_outcome`` — the single-pass helper
``annotate_live_strip`` itself delegates to — and prints a loud ``::warning``
for exactly the MATERIAL outcomes (absent, unparseable, ``publish_served``
failed), while the three benign ones stay exactly as silent as they always
were: paging on "already annotated" or a routine CAS skip would be the
false-alarm factory the falsifier law forbids just as surely as staying quiet
on a real absence was. The classification is read off the SAME read/CAS pass
``annotate_live_strip`` already performs — never a second read — so it cannot
disagree with what was actually written, and nothing about the re-read-last
ordering, the single writer contract, or the dark failure direction above
changes: the caller now REPORTS the dark outcomes it used to have without
altering which ones happen or how the write itself is decided.

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

#: ``_annotate_live_strip_outcome``'s vocabulary. Every value the write attempt
#: can end in, one name each — the caller classifies by NAME, never by
#: re-deriving "was that reason material" from a boolean, so a new outcome added
#: later must be filed into MATERIAL_ANNOTATE_OUTCOMES or it is a silent bug by
#: construction rather than a silent bug by omission.
ANNOTATE_OUTCOME_ANNOTATED = "annotated"                  # wrote the key
ANNOTATE_OUTCOME_ALREADY_ANNOTATED = "already_annotated"  # BENIGN — common tick
ANNOTATE_OUTCOME_DRY_RUN = "dry_run"                      # BENIGN
ANNOTATE_OUTCOME_CAS_SKIP = "cas_skip"                    # BENIGN — the swap did its job
ANNOTATE_OUTCOME_ABSENT = "absent"                        # MATERIAL
ANNOTATE_OUTCOME_UNPARSEABLE = "unparseable"               # MATERIAL
ANNOTATE_OUTCOME_PUBLISH_FAILED = "publish_failed"          # MATERIAL

#: The outcomes the caller must not stay silent on. False here is USUALLY
#: correct (module docstring) — everything NOT in this set is a benign reason
#: to write nothing, and paging on one of those would be the false-alarm
#: factory the falsifier law forbids just as surely as staying quiet on one of
#: THESE would be the 27-day freeze this set exists to stop repeating.
MATERIAL_ANNOTATE_OUTCOMES = frozenset({
    ANNOTATE_OUTCOME_ABSENT, ANNOTATE_OUTCOME_UNPARSEABLE,
    ANNOTATE_OUTCOME_PUBLISH_FAILED,
})


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


def _annotate_live_strip_outcome(path: Path, payload: dict, *,
                                 dry_run: bool = False) -> tuple[bool, str]:
    """``(wrote, outcome)`` — the single read/CAS/write pass, in full.

    THE single source of truth for both the public ``annotate_live_strip``
    (which keeps its historical bool-only contract, unchanged, for every
    existing caller and test) and for ``run()``'s material/benign
    classification (FROZEN SPEC Part B). Splitting the outcome out here rather
    than having the caller re-derive it from a SECOND read is what keeps this
    one pass over the file: a second read could observe different bytes than
    the ones this function's own compare-and-swap actually acted on and
    misclassify a benign CAS skip as a material absence, or the reverse.

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
    an already-correct key writes nothing at all. What changed is that the
    REASON now travels with the ``False``, so a caller can tell "nothing to do"
    from "something is broken" without a second read.
    """
    doc, seen = _read_doc(path)
    if doc is None:
        # Before the first evaluator pass of the day, or on a host with no live
        # plane. Creating the file would hand the surface a prophet artifact
        # with no prophet data in it. The distinction below is diagnostic only
        # — a best-effort existence probe AFTER the read that already decided
        # nothing gets written, never a second determination of whether to
        # write. A race in the few microseconds between them can mislabel the
        # REASON; it can never change what was (not) written.
        outcome = (
            ANNOTATE_OUTCOME_ABSENT if not path.exists()
            else ANNOTATE_OUTCOME_UNPARSEABLE
        )
        return False, outcome
    state = CB.board_state(payload)
    if doc.get(STATE_KEY) == state:
        return False, ANNOTATE_OUTCOME_ALREADY_ANNOTATED  # the common tick
    if dry_run:
        print(f"dry-run: would annotate {path} with {state['rel']} "
              f"({len(state['board']['tickers'])} tickers)", flush=True)
        return False, ANNOTATE_OUTCOME_DRY_RUN
    # COMPARE-AND-SWAP. Re-read LAST, so the evaluator's rewrite is detected
    # here rather than overwritten below.
    if _read_doc(path)[1] != seen:
        print(f"::notice title={_TAG}::{path.name} was rewritten while this "
              "pass was building its key — skipping rather than clobbering the "
              "newer document (the next tick re-annotates)", flush=True)
        return False, ANNOTATE_OUTCOME_CAS_SKIP
    doc[STATE_KEY] = state
    wrote = publish_served(path, doc)
    return wrote, (ANNOTATE_OUTCOME_ANNOTATED if wrote
                   else ANNOTATE_OUTCOME_PUBLISH_FAILED)


def annotate_live_strip(path: Path, payload: dict, *, dry_run: bool = False) -> bool:
    """Merge ``board_state`` into the served prophet_live.json. Never creates it.

    A thin wrapper over :func:`_annotate_live_strip_outcome` that keeps this
    function's historical bool-only contract for every existing caller: ``run()``
    reads the richer ``(wrote, outcome)`` pair directly so it can tell a
    material failure from a benign one (FROZEN SPEC Part B); this name is kept
    for the CAS mechanics tests and any other caller that only ever needed to
    know whether the key was written.
    """
    wrote, _outcome = _annotate_live_strip_outcome(path, payload, dry_run=dry_run)
    return wrote


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
        _wrote, outcome = _annotate_live_strip_outcome(Path(plv), payload, dry_run=dry_run)
        # FROZEN SPEC Part B. False is USUALLY correct here (module docstring) —
        # already-annotated, dry-run and a CAS skip are all silent by design, and
        # paging on any of them would be exactly the false-alarm factory the
        # falsifier law forbids. The three MATERIAL_ANNOTATE_OUTCOMES are the
        # mirror's OWN attempt breaking — the served target absent or
        # unparseable, or its own publish_served failing — and this caller used
        # to discard that boolean outright: the served file did not exist at
        # all for 27 days and nothing on this path said so.
        if outcome in MATERIAL_ANNOTATE_OUTCOMES:
            reason = {
                ANNOTATE_OUTCOME_ABSENT: "the target file is absent",
                ANNOTATE_OUTCOME_UNPARSEABLE: "the target file is unparseable",
                ANNOTATE_OUTCOME_PUBLISH_FAILED: "publish_served returned False",
            }[outcome]
            print(
                f"::warning title={_TAG}::could not annotate {plv} with "
                f"tonight's board_state ({reason}) — the dashboard's live "
                "strip will not paint tonight's picks until this clears",
                flush=True,
            )
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
