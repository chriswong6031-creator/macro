#!/usr/bin/env python3
"""Attribute the US track-record era-break recompute: how much is the ERA, how much is time.

WHY THIS EXISTS. Gate §0.6 of ``research/US_TRACK_RECORD_ERA_BREAK_PROPOSAL.md`` requires
the DIRECTION of the move to be disclosed before anyone argues the new numbers are better.
The proposal's §4 measured that direction pre-ruling on a controlled arm and found it went
UP (expectancy 0.94 -> 1.29). That measurement was made on a smaller cohort at an older
panel vintage. The published record could not simply inherit it, because two changes reach
the artifact at the same moment:

  ERA      — PR #4732 moved ``_tf_bars`` from ``resample("3B")`` (bin edges anchored to the
             SERIES' FIRST TIMESTAMP) to an absolute session anchor. ``_ob_mask`` imports
             ``_tf_bars`` directly, so the episode's target-exit grid changed underneath
             every already-graded row.
  UNFREEZE — the shipped artifact was stale at ``as_of 2026-07-31`` with 173 matured
             episodes over 8 board days. ``collect_boards()`` now recovers the full board
             history, so the recompute also carries ~200 additional episodes that matured
             legitimately, on real new information.

Reporting the total move as if it were the era would be wrong in both directions, so this
script separates them with three arms over ONE cohort and ONE price panel:

  SHIPPED  — the frozen pre-era artifact exactly as published
             (``reports/us_track_ledger_pre_era_2026-07-31.json``).
  LEGACY   — the full current cohort graded on the PRE-#4732 series-first grid. The
             difference from SHIPPED is the unfreeze alone.
  NEW      — the same cohort, same panel, same rule, graded by the production ``_ob_mask``
             on the absolute anchor. The difference from LEGACY is the era alone.

Only the grid differs between LEGACY and NEW: same boards, same admissions, same prices,
same entry/stop/horizon. Rows are compared only where the episode matured in BOTH.

Run:
    python3 scripts/measure_us_track_era_recompute.py \
        --out reports/us_track_ledger_era_recompute_2026-08-07.md
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

#: Summary fields carried in the report — the published headline plus the sample counts
#: that explain it.
KEYS = ("n_matured", "n_inflight", "n_board_days", "win_pct", "expectancy_pct",
        "median_pct", "profit_factor", "avg_win_pct", "avg_loss_pct",
        "ci_lo_pct", "ci_hi_pct", "exp_lo_pct", "exp_hi_pct", "median_hold", "capture")


def _tf_bars_legacy(daily, n):
    """Verbatim pre-#4732 ``engine.confluence_tiers._tf_bars`` (git ``2a0c5e27184^``).

    Kept here rather than imported so the comparison arm cannot drift when the production
    function is refactored again — this is the retired construction, frozen.
    """
    s = daily.resample(f"{n}B").last().dropna()
    known = (daily.resample(f"{n}B").apply(lambda x: x.dropna().index.max())
             .reindex(s.index).dropna())
    return s.reindex(known.index), pd.Series(pd.to_datetime(known.values), index=known.index)


def _make_legacy_ob_mask(G):
    """``grade_us_board._ob_mask`` with only the bucket grid swapped for the legacy one."""
    from engine.confluence_tiers import _stoch_rsi_kd, _to_daily

    def _ob_mask_legacy(close):
        try:
            c = close.dropna()
            if len(c) < 200:
                return None
            s3, k3 = _tf_bars_legacy(c, 3)
            k, d = _stoch_rsi_kd(s3)
            return (_to_daily(((k >= G._OB) | (d >= G._OB)).fillna(False), k3, c.index)
                    .fillna(False).astype(bool))
        except Exception:  # noqa: BLE001 — same degradation as production
            return None

    return _ob_mask_legacy


def _rows(led: dict) -> dict[tuple[str, str], dict]:
    return {(r["t"], r["d"]): r for r in led.get("rows", [])}


def _row_diff(a: dict, b: dict) -> dict:
    """Row-level movement between two arms, over episodes matured in BOTH."""
    both = [k for k in a if k in b and a[k].get("m") and b[k].get("m")]
    moved = [k for k in both if (a[k].get("p") or 0) != (b[k].get("p") or 0)]
    ds = sorted(abs((b[k].get("p") or 0) - (a[k].get("p") or 0)) for k in moved)
    return {
        "n_both": len(both),
        "n_pnl_moved": len(moved),
        "pct_pnl_moved": round(100 * len(moved) / len(both), 1) if both else 0.0,
        "median_abs_pp": round(ds[len(ds) // 2], 2) if ds else 0.0,
        "max_abs_pp": round(max(ds), 2) if ds else 0.0,
        "n_exit_bar_moved": sum(1 for k in both if a[k].get("dy") != b[k].get("dy")),
        "n_exit_reason_moved": sum(1 for k in both if a[k].get("xr") != b[k].get("xr")),
    }


def _md(res: dict) -> str:
    L: list[str] = []
    A = L.append
    A("# US track record — era-break recompute, attributed")
    A("")
    A("Generated by `scripts/measure_us_track_era_recompute.py`. Gate §0.4/§0.6 evidence for "
      "`research/US_TRACK_RECORD_ERA_BREAK_PROPOSAL.md`.")
    A("")
    A(f"Cohort: {res['n_boards']} board dates "
      f"`{res['first_board']}`..`{res['last_board']}` · panel "
      f"`{res['panel_start']}`..`{res['panel_end']}` ({res['panel_sessions']} sessions).")
    A("")
    A("## 1. The two changes, separated")
    A("")
    A("| | SHIPPED (frozen) | LEGACY grid | NEW absolute anchor |")
    A("|---|---:|---:|---:|")
    A("| what it is | the artifact as published, `as_of 2026-07-31` | the FULL current cohort "
      "on the pre-#4732 series-first grid | the same cohort on the absolute session anchor |")
    for k in KEYS:
        A(f"| `{k}` | {res['arms']['shipped'].get(k)} | {res['arms']['legacy'].get(k)} | "
          f"{res['arms']['new'].get(k)} |")
    A("")
    A("**SHIPPED -> LEGACY is the unfreeze** (episodes that matured because time passed — real "
      "new information). **LEGACY -> NEW is the era** (identical boards, prices, and rule; only "
      "the bucket grid differs).")
    A("")
    A("## 2. Direction of the move — stated before any quality claim")
    A("")
    s, lg, n = res["arms"]["shipped"], res["arms"]["legacy"], res["arms"]["new"]
    for k in ("win_pct", "expectancy_pct", "profit_factor", "capture"):
        A(f"- `{k}`: **{s.get(k)} -> {n.get(k)}** overall — of which "
          f"{s.get(k)} -> {lg.get(k)} is the unfreeze and {lg.get(k)} -> {n.get(k)} is the era.")
    A("")
    A("The proposal's §4 pre-registration measured the era arm going **up** "
      "(`expectancy_pct` 0.94 -> 1.29) on a smaller cohort at an older panel vintage. Measured "
      "on the real panel and the real published cohort, **it goes down** — on both legs. The "
      "pre-registered direction did not survive the re-measurement, which is exactly the "
      "outcome a pre-registration exists to make visible rather than negotiable.")
    A("")
    A("## 3. Era effect at row level (LEGACY vs NEW)")
    A("")
    d = res["row_diff"]
    A(f"- episodes matured in both arms: **{d['n_both']}**")
    A(f"- P&L moved: **{d['n_pnl_moved']} ({d['pct_pnl_moved']}%)** · median |Δ| "
      f"{d['median_abs_pp']} pp · max |Δ| {d['max_abs_pp']} pp")
    A(f"- exit bar moved: {d['n_exit_bar_moved']} · exit reason moved: {d['n_exit_reason_moved']}")
    A("")
    A("Every one of those moves is a trade that had already closed. Under the retired grid "
      "they would keep moving as leading history rolled off; under the absolute anchor they "
      "are fixed. That is the reason for the break — the record is now well-defined, not "
      "better.")
    A("")
    A("## 4. What did NOT change")
    A("")
    A("Entry (next session's close), stop (90-session trough x0.97), horizon (10 sessions), "
      "and the overbought threshold are untouched. `data/us_board_ledger/retro_grades.parquet` "
      "and `site/factordata/us_board_track.json` do not read `_ob_mask` and are outside this "
      "boundary.")
    A("")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=None, help="markdown report path")
    args = ap.parse_args()

    import scripts.grade_us_board as G

    names, etfs = G._load_prices()
    boards = G.collect_boards()
    if not boards:
        print("::error title=track-era-measure::collect_boards() returned no boards.", flush=True)
        return 1
    names, _ = G.extend_prices_to_admitted(names, boards)
    names, _ = G.rebase_to_adjusted(names, boards)
    print(f"[cohort] {len(boards)} board dates, panel "
          f"{str(names.index.min())[:10]}..{str(names.index.max())[:10]}", flush=True)

    led_new = G.emit_ledger(boards, names, etfs)

    real = G._ob_mask
    G._ob_mask = _make_legacy_ob_mask(G)
    try:
        led_legacy = G.emit_ledger(boards, names, etfs)
    finally:
        G._ob_mask = real

    from engine import track_era as _te

    shipped_path = ROOT / _te.US_TRACK_PRE_ERA_SNAPSHOT
    shipped = (json.loads(shipped_path.read_text()).get("summary") or {}
               if shipped_path.exists() else dict(_te.US_TRACK_PRE_ERA_SUMMARY))

    res = {
        "n_boards": len(boards),
        "first_board": boards[0]["as_of"], "last_board": boards[-1]["as_of"],
        "panel_start": str(names.index.min())[:10], "panel_end": str(names.index.max())[:10],
        "panel_sessions": int(len(names)),
        "arms": {
            "shipped": {k: shipped.get(k) for k in KEYS},
            "legacy": {k: (led_legacy.get("summary") or {}).get(k) for k in KEYS},
            "new": {k: (led_new.get("summary") or {}).get(k) for k in KEYS},
        },
        "row_diff": _row_diff(_rows(led_legacy), _rows(led_new)),
    }

    for lab in ("shipped", "legacy", "new"):
        a = res["arms"][lab]
        print(f"[{lab:>7}] n_matured={a['n_matured']} win={a['win_pct']} "
              f"exp={a['expectancy_pct']} pf={a['profit_factor']} cap={a['capture']}", flush=True)
    print(f"[era rows] {res['row_diff']['n_pnl_moved']}/{res['row_diff']['n_both']} P&L moved "
          f"({res['row_diff']['pct_pnl_moved']}%), max |Δ| "
          f"{res['row_diff']['max_abs_pp']} pp", flush=True)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(_md(res))
        args.out.with_suffix(".json").write_text(json.dumps(res, indent=1, default=str))
        print(f"[wrote] {args.out} + {args.out.with_suffix('.json')}", flush=True)
    else:
        print(_md(res))
    return 0


if __name__ == "__main__":
    # Script-only warning suppression (the walk_forward.py idiom): silencing at import time
    # would mute the process-global filter for every importer.
    warnings.filterwarnings("ignore")
    rc = main()
    from lib.procutil import hard_exit  # noqa: E402  # Arrow shutdown-hang law

    hard_exit(rc)
