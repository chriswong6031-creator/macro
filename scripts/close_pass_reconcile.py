"""scripts.close_pass_reconcile — grade the evening board against the record.

Runs after the nightly board of record lands and publishes the per-name
provisional → nightly confirmation delta. This is what makes the evening board
a claim that gets marked rather than a second opinion, and it costs one set
difference (see ``engine.close_pass.reconcile`` for what "adjusted" means and
why it is not a rank diff).

The receipt is a RUNTIME artifact on R2, exactly like the board it grades. It
advances no ledger and writes no ``data/`` path — the nightly is the sole writer
of record, and a lane that graded the record by writing to it would be marking
its own homework.

Usage:
  python -m scripts.close_pass_reconcile
  python -m scripts.close_pass_reconcile --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.close_pass.reconcile import (  # noqa: E402
    board_state_payload,
    confirmation_receipt,
)
from engine.prophet_live import r2io  # noqa: E402
from scripts.close_pass_publish import BOARD_KEY  # noqa: E402

#: Where the receipt lands. The nightly render reads it SERVER-SIDE to build the
#: spec's state-2 confirmation line — it is never fetched by the browser, so it
#: needs no live-plane mirror and no serving-policy entry.
RECEIPT_KEY = "live_flow/us_board_confirmation.json"
#: The nightly board of record, as committed by build_stock_library.
NIGHTLY_BOARD = "site/factordata/us_standouts.json"

_TAG = "close-pass"


def load_nightly(root: Path) -> dict | None:
    try:
        return json.loads((root / NIGHTLY_BOARD).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"::warning title={_TAG}::nightly board unreadable ({exc}) — "
              "no receipt", flush=True)
        return None


def board_state_for(nightly: dict | None, *, now: datetime | None = None,
                    fetch=None) -> dict | None:
    """The ``board_state`` contract for a board doc IN HAND, or None.

    THE SAME-BUILD HOP. ``run()`` below grades the board as it exists ON DISK,
    which is the right shape for an artifact but the wrong shape for a render:
    the receipt for session N can only be published after session N's board
    lands, so a render that READ the published receipt would forever be showing
    session N-1's figures under session N's cards — last night's arithmetic
    under tonight's names. So the render does not read the receipt; it computes
    one, here, from the board dict it is about to render, at the moment both
    halves exist (the evening board has been on R2 since ~16:25 ET, and the
    nightly board of record has just been built).

    NOT A SECOND DEFINITION. ``confirmation_receipt`` is imported, never
    reimplemented, and both call sites feed it the same two immutable documents
    — the evening board's R2 object, and tonight's ``us_standouts`` — so the
    rendered receipt and the published artifact cannot disagree about a night.

    Every ordering hazard is answered by ONE property already inside
    ``confirmation_receipt``: the two boards must name the same session. A
    caller holding LAST night's board (the nightly's first pass reads the prior
    build's file), or a night with no evening board at all (``behind``), or an
    edge-cached provisional from a previous session — all present as an ``as_of``
    disagreement, and all get None. No pairing this cannot vouch for renders.

    ``fetch`` resolves at CALL time, not at def time: the render reaches this
    through an import inside ``build_site``, so a default bound at import would
    make the one network hop in the chain unreplaceable and force the render
    test to stub the hop itself — proving the stub rather than the wiring.
    """
    if not nightly:
        return None
    get = fetch or r2io.get_json
    return board_state_payload(
        confirmation_receipt(get(BOARD_KEY), nightly, built_at=now))


def run(root: Path, *, now: datetime, dry_run: bool = False,
        fetch=r2io.get_json, publish=r2io.put_json) -> int:
    provisional = fetch(BOARD_KEY)
    nightly = load_nightly(root)
    receipt = confirmation_receipt(provisional, nightly, built_at=now)

    if receipt is None:
        # The ordinary case on a `behind` night: no evening board published, so
        # there is nothing to countersign. Publishing an empty or stale receipt
        # would put figures under a board they do not describe.
        print(f"::notice title={_TAG}::no reconcilable pair "
              f"(provisional as_of={(provisional or {}).get('as_of')!r}, "
              f"nightly as_of={(nightly or {}).get('as_of')!r}) — no receipt",
              flush=True)
        return 0

    print(f"{_TAG} {receipt['as_of']}: {receipt['n_confirmed']} confirmed, "
          f"{receipt['n_adjusted']} adjusted, {receipt['n_dropped']} dropped "
          f"of {receipt['n_total']} (+{receipt['detail']['n_added']} added)",
          flush=True)
    if dry_run:
        print("dry-run: nothing published", flush=True)
        return 0
    if not publish(RECEIPT_KEY, receipt):
        print(f"::warning title={_TAG}::R2 PUT {RECEIPT_KEY} failed — "
              "the render will find no receipt and render no receipt line",
              flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Provisional → nightly confirmation delta")
    ap.add_argument("--now", default=None, help="ISO clock override (naive = UTC)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if args.now:
        now = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        now = (now.replace(tzinfo=timezone.utc) if now.tzinfo is None
               else now.astimezone(timezone.utc))
    else:
        now = datetime.now(timezone.utc)
    return run(ROOT, now=now, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
