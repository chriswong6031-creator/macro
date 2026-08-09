#!/usr/bin/env python3
"""Re-measure and republish ``site/factordata/us_track_ledger.json`` alone.

WHY A SEPARATE ENTRYPOINT. Gate §0.4 of
``research/US_TRACK_RECORD_ERA_BREAK_PROPOSAL.md`` requires the era-break re-measurement to
run on the REAL panel and land in the same PR as the ruling. ``grade_us_board.py --nightly``
would do it, but it also appends a board snapshot, re-grades and rewrites
``retro_grades.parquet``, and drives the v2 lane — stores the nightly owns and this charter
explicitly does not touch (§6: "No change to retro_grades.parquet or us_board_track.json").

So this script walks the SAME load path as ``grade_us_board.main`` up to the point where
the ledger is emitted, calls the real ``emit_ledger``, and writes exactly one file. No
snapshot is appended, no parquet store is written, no other artifact moves.

The write goes through ``engine.track_ledger.atomic_write``, so the era guard applies here
too — this script cannot publish an unstamped re-bake either.

Run:
    python3 scripts/recompute_us_track_ledger.py            # write
    python3 scripts/recompute_us_track_ledger.py --dry-run  # print the headline only
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

#: Fields printed as the before/after receipt — the numbers a reader actually sees.
_RECEIPT_KEYS = ("n_matured", "n_inflight", "n_board_days", "win_pct", "expectancy_pct",
                 "median_pct", "profit_factor", "avg_win_pct", "avg_loss_pct",
                 "ci_lo_pct", "ci_hi_pct", "exp_lo_pct", "exp_hi_pct",
                 "median_hold", "capture")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="compute and print the headline without writing the artifact")
    args = ap.parse_args()

    from engine import track_ledger as _tl
    from scripts.grade_us_board import (
        LEDGER_JSON, _load_prices, collect_boards, emit_ledger,
        extend_prices_to_admitted, rebase_to_adjusted,
    )

    before = {}
    if LEDGER_JSON.exists():
        try:
            before = (json.loads(LEDGER_JSON.read_text()) or {}).get("summary") or {}
        except Exception as e:  # noqa: BLE001 — a corrupt predecessor is not fatal here
            print(f"[before] unreadable ({e})", flush=True)

    names, etfs = _load_prices()
    receipt: dict = {}
    boards = collect_boards(receipt)
    if not boards:
        print("::error title=track-ledger-recompute::collect_boards() returned no boards — "
              "refusing to publish an empty record.", flush=True)
        return 1
    print(f"[boards] {len(boards)} as_of dates {boards[0]['as_of']}..{boards[-1]['as_of']} "
          f"({receipt.get('n_from_snapshots')} from snapshots, {receipt.get('n_from_git')} "
          f"from {receipt.get('n_git_revisions')} git revision(s))", flush=True)

    # The production order, exactly: admitted-name recovery, then the adjusted-basis
    # rebase. Skipping either would measure a panel the nightly never grades.
    names, price_receipt = extend_prices_to_admitted(names, boards)
    print(f"[prices] {names.shape[1]} priced tickers "
          f"(+{price_receipt['n_recovered_from_admitted_store']} recovered, "
          f"{price_receipt['n_unresolved']} unresolvable)", flush=True)
    names, basis = rebase_to_adjusted(names, boards)
    print(f"[price_basis] {basis['n_columns_rebased']} columns re-based; "
          f"{basis['names_on_unadjusted_basis']} left on the raw cache", flush=True)
    print(f"[panel] {str(names.index.min())[:10]}..{str(names.index.max())[:10]} "
          f"({len(names)} sessions)", flush=True)

    ledger = emit_ledger(boards, names, etfs)
    after = ledger.get("summary") or {}
    meta = ledger.get("meta") or {}

    print(f"[era] anchor_era={meta.get('anchor_era')} "
          f"pre_era={(meta.get('pre_era') or {}).get('anchor_era')} "
          f"@{(meta.get('pre_era') or {}).get('as_of')}", flush=True)
    print(f"[as_of] {before.get('__as_of__', '')}{ledger.get('as_of')} "
          f"state={ledger.get('state')} rows={meta.get('n_total')}", flush=True)
    print("[headline] key: before -> after")
    for k in _RECEIPT_KEYS:
        b, a = before.get(k), after.get(k)
        flag = "" if b == a else "   <-- moved"
        print(f"  {k:>18}: {b} -> {a}{flag}")

    if args.dry_run:
        print("[dry-run] nothing written", flush=True)
        return 0

    if not _tl.atomic_write(LEDGER_JSON, ledger):
        print("::error title=track-ledger-recompute::atomic_write refused or failed — "
              "the published file is unchanged.", flush=True)
        return 1
    print(f"[wrote] {LEDGER_JSON}", flush=True)
    return 0


if __name__ == "__main__":
    # Script-only warning suppression (the walk_forward.py idiom): silencing at import
    # time would mute the filter for every importer.
    warnings.filterwarnings("ignore")
    rc = main()
    from lib.procutil import hard_exit  # noqa: E402  # Arrow shutdown-hang law

    hard_exit(rc)
