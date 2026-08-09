"""A2 live proof — committed US boards replayed through the BASE and HEAD rank module.

ANTICIPATION §6.2.  Nothing here is simulated: the "before" side is
the pinned :data:`BASE_SHA` ``engine/us_board_rank.py`` materialised to a temp file and imported
alongside the working-tree module, so both sides are real code running the same
committed rows.  Rows come from committed artifacts only and nothing is written back
into ``site/``.

Three receipts:

1. **The ext_z blackout policy.**  The 2026-08-06 board (69/69 rows with no extension
   reading) published ``featured: 0``.  Replayed under HEAD it features again, every
   featured row flagged ``ext_unknown``, and the outage raises a ``::warning``.  #4979
   has since coverage-anchored and age-bounded the extension reader, preventing that
   historical sparse-row selection; this frozen board still tests what happens when a
   reading is honestly absent or the bounded reader withholds the panel.
2. **The map re-order.**  The current committed board, ranked under both maps, old
   rank -> new rank.  HEAD's map is FLAT across the five admissible statuses
   (ANTICIPATION v1 amendment, after the §6.6 first run read adverse to the CN
   ordering), so the movement here is the collapse of the trend-tape ordering AMONG
   admissible rows — not a patience-first lift, and not a demotion of anything.
   NOTHING SCORES LOWER under HEAD: the five admissible statuses all pay 1.0 and every
   refused-class value is untouched (``buy_soon`` was briefly cut to 0.35 on CN's
   table and restored to its trend-tape 0.8 by orchestrator ruling 2026-08-09 — the
   ``buy_soon`` rows in PROOF 2 print identical old and new scores, which is that
   restoration's receipt).
3. **What the stage bucket still hides.**  The sort key is
   ``(stage_rank, -score, ticker)``, so a ``setting_up`` row cannot outrank a ``live``
   row however high it scores.  Even under the flat map some ``bounce_wait`` rows
   outscore every ``live`` row and still render ~30 places down.  This is the
   measurement that says the stage gate — not the entry map — is the binding
   constraint on §6.2.

Usage (from the repo root)::

    TZ=UTC python3 research/prophet_us_audit/a2_ladder_replay.py
    TZ=UTC python3 research/prophet_us_audit/a2_ladder_replay.py --base <sha>

Every input is PINNED to a commit, including the "before" side.  An earlier draft read
the base module from ``origin/main``, which is a MOVING ref: main takes ~24 nightly
commits a day here, so re-running the same script a day later silently measured a
different baseline and printed the same headings over it — a receipt nobody can
reproduce is not a receipt.  ``--base`` names the commit explicitly and
:data:`BASE_SHA` records the one these committed numbers were produced against.
"""
from __future__ import annotations

import argparse
import copy
import datetime as _dt
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# The 2026-08-06 board — the 0/69 featured blackout the parity anatomy measured.
DARK_BOARD_SHA = "3cbef39a6ea"

#: The "before" side, PINNED.  This is the ``origin/main`` tip this receipt's committed
#: numbers were measured against — not a symbolic ref, so a re-run reproduces them.
#: Override with ``--base`` to re-measure against a newer main; if you do, update this
#: constant in the same commit as the numbers, or the two disagree.
BASE_SHA = "fd9751d580db48d03eaaa108a8b5cf21534fad59"

LIVE_BOARD = REPO / "site" / "factordata" / "us_standouts.json"

#: Results land beside the script, ``<script>_results.json`` — the convention every
#: other study in this directory follows (``ignition_standins_results.json``,
#: ``label_grading_battery_results.json``, ...).  Printed output is for reading; this
#: is what a later session diffs against.
RESULTS_PATH = Path(__file__).with_name("a2_ladder_replay_results.json")

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _load_base_module(sha: str):
    """Import the BASE commit's us_board_rank under its own name, not shadowing HEAD's."""
    src = subprocess.run(
        ["git", "show", f"{sha}:engine/us_board_rank.py"],
        cwd=REPO, capture_output=True, text=True, check=True).stdout
    path = Path(tempfile.mkdtemp()) / "_base_us_board_rank.py"
    path.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("_base_us_board_rank", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_base_us_board_rank"] = module
    spec.loader.exec_module(module)
    return module


def _board_from_sha(sha: str) -> dict:
    blob = subprocess.run(
        ["git", "show", f"{sha}:site/factordata/us_standouts.json"],
        cwd=REPO, capture_output=True, text=True, check=True).stdout
    return json.loads(blob)


def _replay(module, board: dict) -> tuple[list[dict], dict, str]:
    """Score a committed buy lane exactly the way build_stock_library does."""
    rows = copy.deepcopy(board["buy"])
    buf = io.StringIO()
    with redirect_stdout(buf):
        scored = module.score_rows(
            rows,
            board_asof=board.get("as_of"),
            bottom_watch_stage=module.STAGE_BASING,
        )
        block = module.ranking_block(scored)
    return scored, block, buf.getvalue()


def _status(row: dict) -> str:
    return str((row.get("entry_signal") or {}).get("status") or "—")


def _first_warning(text: str) -> str:
    return next((ln for ln in text.splitlines() if ln.startswith("::warning")), "NONE")


def proof_ext_z(base, head) -> dict:
    print("=" * 78)
    print(f"PROOF 1 — ext_z blackout: committed 2026-08-06 board ({DARK_BOARD_SHA})")
    print("=" * 78)
    dark = _board_from_sha(DARK_BOARD_SHA)
    _b_rows, b_block, _ = _replay(base, dark)
    h_rows, h_block, h_out = _replay(head, dark)
    n = len(dark["buy"])
    # The engine's OWN predicate, not `is None`.  The 2026-07-31 defect delivered NaN
    # rather than a missing key, and `r.get("ext_z") is None` reads a NaN as a reading —
    # so a hand-rolled check here would have UNDERCOUNTED the very outage this proof
    # exists to measure, while the module it is auditing counted it correctly.
    unknown = sum(1 for r in dark["buy"] if head.ext_unknown(r))
    print(f"board as_of      : {dark['as_of']}   buy rows: {n}")
    print(f"ext_z unknown    : {unknown}/{n}")
    print(f"featured BEFORE  : {b_block['featured_count']}  "
          f"(blocked_unknown_extension="
          f"{b_block['featured_blocked_unknown_extension']})")
    print(f"featured AFTER   : {h_block['featured_count']}  "
          f"ext_unknown_coverage={h_block['ext_unknown_coverage']}")
    print("featured cohort  : "
          + ", ".join(f"{r['ticker']}({_status(r)})" for r in h_rows if r["featured"]))
    print("annotation       : " + _first_warning(h_out))
    print(f"committed artifact says: featured_count="
          f"{dark['ranking']['featured_count']}  blocked_unknown_extension="
          f"{dark['ranking']['featured_blocked_unknown_extension']}")
    return {
        "board_sha": DARK_BOARD_SHA,
        "board_asof": dark["as_of"],
        "buy_rows": n,
        "ext_unknown": unknown,
        "featured_before": b_block["featured_count"],
        "featured_after": h_block["featured_count"],
        "ext_unknown_coverage_after": h_block["ext_unknown_coverage"],
        "featured_cohort_after": [
            {"ticker": r["ticker"], "status": _status(r)}
            for r in h_rows if r["featured"]],
        "annotation": _first_warning(h_out),
        "committed_featured_count": dark["ranking"]["featured_count"],
    }


def proof_ladder(base, head) -> tuple[list[dict], dict]:
    print()
    print("=" * 78)
    print("PROOF 2 — ladder re-order on the current committed board")
    print("=" * 78)
    live = json.loads(LIVE_BOARD.read_text(encoding="utf-8"))
    lb_rows, lb_block, _ = _replay(base, live)
    lh_rows, lh_block, lh_out = _replay(head, live)
    old_rank = {r["ticker"]: r["score_rank"] for r in lb_rows}
    old_score = {r["ticker"]: r["prophet"]["score"] for r in lb_rows}
    print(f"board as_of {live['as_of']}   buy rows {len(live['buy'])}   "
          f"featured {lb_block['featured_count']} -> {lh_block['featured_count']}")
    print(f"{'new':>4} {'old':>4}  {'ticker':<8} {'status':<16} {'stage':<11} "
          f"{'old':>7} {'new':>7}")
    for row in lh_rows[:10]:
        t = row["ticker"]
        print(f"{row['score_rank']:>4} {old_rank.get(t, '—'):>4}  {t:<8} "
              f"{_status(row):<16} {row['stage']:<11} "
              f"{old_score.get(t, 0.0):>7.1f} {row['prophet']['score']:>7.1f}")
    moved = sum(1 for r in lh_rows if old_rank.get(r["ticker"]) != r["score_rank"])
    print(f"rows whose rank moved: {moved}/{len(lh_rows)}")
    print("selection_era    : " + lh_block["selection_era"])
    print("annotation       : " + _first_warning(lh_out))
    return lh_rows, {
        "board_asof": live["as_of"],
        "buy_rows": len(live["buy"]),
        "featured_before": lb_block["featured_count"],
        "featured_after": lh_block["featured_count"],
        "rows_whose_rank_moved": moved,
        "selection_era": lh_block["selection_era"],
        "top10": [
            {"new_rank": r["score_rank"], "old_rank": old_rank.get(r["ticker"]),
             "ticker": r["ticker"], "status": _status(r), "stage": r["stage"],
             "old_score": round(old_score.get(r["ticker"], 0.0), 1),
             "new_score": round(r["prophet"]["score"], 1)}
            for r in lh_rows[:10]],
    }


def proof_stage_gate(head, rows: list[dict]) -> dict:
    print()
    print("=" * 78)
    print("PROOF 3 — what the STAGE bucket still hides")
    print("=" * 78)
    print("sort key is (stage_rank, -score, ticker): a `setting_up` row cannot "
          "outrank a `live` row however high it scores.")
    by_score = sorted(rows, key=lambda r: -r["prophet"]["score"])
    print(f"{'score#':>6} {'board#':>6}  {'ticker':<8} {'status':<16} "
          f"{'stage':<11} {'score':>6}")
    for i, row in enumerate(by_score[:10], start=1):
        print(f"{i:>6} {row['score_rank']:>6}  {row['ticker']:<8} "
              f"{_status(row):<16} {row['stage']:<11} "
              f"{row['prophet']['score']:>6.1f}")
    patience = [r for r in rows
                if _status(r) in ("bounce_wait", "wait_pullback", "hold")]
    top_live = max((r["prophet"]["score"] for r in rows
                    if r["stage"] == head.STAGE_LIVE), default=0.0)
    outscoring = [r for r in patience if r["prophet"]["score"] > top_live]
    print(f"patience-status rows on the board: {len(patience)}")
    print(f"  ... outscoring the best `live` row ({top_live:.1f}): {len(outscoring)}")
    return {
        "top_live_score": round(top_live, 1),
        "patience_rows": len(patience),
        "patience_rows_outscoring_best_live": len(outscoring),
        "by_score_top10": [
            {"score_rank": i, "board_rank": r["score_rank"], "ticker": r["ticker"],
             "status": _status(r), "stage": r["stage"],
             "score": round(r["prophet"]["score"], 1)}
            for i, r in enumerate(by_score[:10], start=1)],
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default=BASE_SHA,
                    help="commit whose engine/us_board_rank.py is the 'before' side "
                         f"(default: the pinned {BASE_SHA[:11]})")
    ap.add_argument("--out", default=str(RESULTS_PATH),
                    help="results JSON path (default: beside this script)")
    args = ap.parse_args(argv)

    base = _load_base_module(args.base)
    from engine import us_board_rank as head  # noqa: PLC0415 — after sys.path setup

    print(f"base commit      : {args.base}")
    p1 = proof_ext_z(base, head)
    rows, p2 = proof_ladder(base, head)
    p3 = proof_stage_gate(head, rows)

    results = {
        # Which code produced these numbers, on both sides.  A results file that does
        # not name its own baseline cannot be compared to the next one.
        "generated_utc": _dt.datetime.now(_dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "base_sha": args.base,
        "head_sha": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO,
            capture_output=True, text=True, check=True).stdout.strip(),
        "head_selection_era": head.SELECTION_ERA,
        "head_entry_value": dict(head._ENTRY_VALUE),
        "proof_1_ext_z_blackout": p1,
        "proof_2_ladder_reorder": p2,
        "proof_3_stage_gate": p3,
    }
    out = Path(args.out)
    out.write_text(json.dumps(results, indent=2, sort_keys=False) + "\n",
                   encoding="utf-8")
    print()
    print(f"results written  : {out.relative_to(REPO)}")


if __name__ == "__main__":
    main()
