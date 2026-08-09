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

from engine.close_pass.reconcile import confirmation_receipt  # noqa: E402
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
