"""ETF consensus board — nightly snapshot + forward grader (masterplan §3 W3).

Entry point for the nightly step in ``.github/workflows/daily.yml``:

    python -m scripts.grade_etf_board --nightly

What one run does, in order:

  1. RECOMPUTE the consensus board exactly as ``etfs.html`` builds it —
     ``engine.holdings_signals.all_etf_signals`` → ``engine.etf_board.drop_cash`` →
     ``engine.etf_consensus.consensus_favored``. Recomputing (rather than parsing the
     rendered page or the premium payload) keeps the fire log honest when the page's
     tier gate withholds rows, and it costs nothing new: the same engines, off the
     render path, on the nightly's own clock.
  2. SNAPSHOT the top-N of that board into ``data/etf_board_ledger/snapshots.jsonl``,
     stamped with the board's DATA date (newest holdings snapshot across the fleet),
     keep-FIRST per (as_of, ticker). LANE-GATED — see engine/etf_board_ledger.py.
  3. GRADE every matured (board date × ticker × horizon) at 5/21/63 trading days,
     next-bar fill, absolute and vs SPY, into ``retro_grades.parquet``. Price columns
     freeze at first grade; a re-run never restates a published measurement.
  4. PROJECT a small display artifact, ``site/factordata/etf_board_track.json``, for
     the Calibration Lab's forward-windows tile.

Display tier, context only. Nothing here feeds a rank, a score, a gate or a size on
etfs.html — it is the evidence a future weighting promotion would have to be
gauntleted against (masterplan §4), and until that evidence exists the surface says
"collecting".

Off-lane (``COLLECT_LANE`` != nightly) the two ``data/`` writes are refused and the
run degrades to a read-only projection of whatever is already committed.

    python -m scripts.grade_etf_board --nightly --quiet
    python -m scripts.grade_etf_board --ledger-dir /tmp/scratch --track-path /tmp/t.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from engine import etf_board_ledger as ebl  # noqa: E402


def collect_board(limit: int | None = None) -> list[dict]:
    """Tonight's consensus board rows, richest-first, or [] when unavailable.

    Every import is LOCAL: the holdings engines pull config, parquet stores and the
    price ladder, and this module must stay importable (and unit-testable) without
    any of them.
    """
    try:
        from engine.holdings_signals import all_etf_signals
    except Exception as exc:  # noqa: BLE001
        print(f"[etf_board] holdings engine unavailable ({exc})", flush=True)
        return []
    try:
        rows = all_etf_signals()
    except Exception as exc:  # noqa: BLE001
        print(f"[etf_board] all_etf_signals failed ({exc})", flush=True)
        return []
    try:
        from engine.etf_board import drop_cash
        rows = drop_cash(rows)
    except Exception as exc:  # noqa: BLE001 — cash filtering is additive
        print(f"[etf_board] drop_cash skipped ({exc})", flush=True)
    try:
        from engine.etf_consensus import consensus_favored
        return consensus_favored(rows, limit=limit) if limit else consensus_favored(rows)
    except Exception as exc:  # noqa: BLE001
        print(f"[etf_board] consensus_favored failed ({exc})", flush=True)
        return []


def warn_if_no_board(favored: list[dict], as_of: str | None, *, nightly: bool) -> bool:
    """A night that logs nothing is the defect underneath the defect — say so.

    Bare line-start print, never a logger: every logger here prefixes the line and
    GitHub silently drops an annotation that does not start the line (house law).
    """
    if not nightly:
        return False
    if favored and as_of:
        return False
    reason = ("no holdings snapshot exists in the store" if not as_of
              else "the consensus board recomputed to zero rows")
    print("::warning title=etf-board-ledger-no-accrual::"
          f"ETF board ledger recorded NOTHING tonight — {reason}. "
          "The forward ledger only advances in the nightly, so a silent night is a "
          "permanent hole in the record.", flush=True)
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nightly", action="store_true",
                    help="snapshot tonight's board before grading (cron entry point)")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--ledger-dir", default=None,
                    help="override the DATA ROOT the ledger lives under (scratch runs)")
    ap.add_argument("--track-path", default=None,
                    help="override the display artifact path (scratch runs)")
    ap.add_argument("--top-n", type=int, default=ebl.TOP_N,
                    help=f"board rows logged per night (default {ebl.TOP_N})")
    args = ap.parse_args(argv)

    base_dir = args.ledger_dir
    quiet = args.quiet

    as_of = ebl.board_asof(base_dir=base_dir)
    favored = collect_board() if args.nightly else []
    if args.nightly and not quiet:
        print(f"[board] as_of={as_of} · {len(favored)} consensus rows recomputed")
    warn_if_no_board(favored, as_of, nightly=args.nightly)

    n_new = 0
    if args.nightly:
        n_new = ebl.append_snapshot(favored, as_of, base_dir=base_dir, top_n=args.top_n)
        if not quiet:
            gate = "on-lane" if ebl.lane_open() else "OFF-LANE (no write)"
            print(f"[snapshot] {n_new} row(s) appended for as_of={as_of} "
                  f"→ {ebl.snapshots_path(base_dir)} [{gate}]")

    records = ebl.load_snapshots(base_dir)
    if not records:
        if not quiet:
            print("[grade] fire log is empty — nothing to grade yet")
    fresh = ebl.grade_snapshots(records)
    full = ebl.merge_grades(fresh, base_dir=base_dir)
    if not quiet:
        n_graded = int(full["ret"].notna().sum()) if not full.empty and "ret" in full else 0
        print(f"[grade] {len(full)} ledger row(s), {n_graded} graded "
              f"→ {ebl.retro_path(base_dir)}")

    track = ebl.build_track(records, full, as_of=as_of)
    path = ebl.write_track(track, args.track_path)
    if not quiet:
        size = path.stat().st_size
        print(f"[track] wrote {path} ({size} bytes; "
              f"{track['n_boards_logged']} board date(s), "
              f"{track['n_graded_total']} graded row(s), "
              f"collecting={track['collecting']})")
        for h in ebl.HORIZONS:
            b = track["per_horizon"][f"h{h}"]
            print(f"  h{h}d: n_graded={b['n_graded']} pending={b['n_pending']} "
                  f"ahead={b['n_ahead']}/{b['n_vs_bench']} "
                  f"median_excess={b['median_excess_bench']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
