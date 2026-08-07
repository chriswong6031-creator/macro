#!/usr/bin/env python3
"""Measure how far the PUBLISHED US track record moves when only LEADING history changes.

WHY THIS EXISTS. ``scripts/grade_us_board._ob_mask`` is the incumbent episode's TARGET
EXIT leg in ``emit_ledger`` — the 3D StochRSI overbought flag that decides which bar an
episode sells on. It reads ``engine.confluence_tiers._tf_bars(c, 3)``, i.e.
``daily.resample("3B")``, whose bin edges anchor to the SERIES' FIRST TIMESTAMP. The
grader calls it on the full rolling close cache
(``grade_us_board`` ``_ob_cache[tk] = _ob_mask(ser)``), and the smallcap/midcap
``data/*/_closes_cache.parquet`` stores are a ROLLING window: their first date moved
2023-06-27 -> 2023-07-03 across three sessions in early August 2026.

So each night, as the cache's start rolls, every 3D bucket in the WHOLE history re-phases.
Overbought flags from weeks ago flip, the exit bar moves, and the realised P&L of episodes
that closed long ago changes — with no new information about those episodes. The published
artifact ``site/factordata/us_track_ledger.json`` (Track-record dialog + the hero win-rate
and expectancy on the Track-record page) is therefore not stable under re-grading.

Causal it is — a 3D bucket is only readable once complete, so it never peeks. Stable it is
not. Those are different properties and the docstring used to claim only the first.

WHAT THIS MEASURES. Two arms, because a night-to-night diff alone cannot separate the
anchor from ordinary vendor revisions:

  NATURAL   (``--rev-a`` vs ``--rev-b``) — re-grade under two real collection commits.
            This is what actually happens to the published numbers overnight. It mixes
            the start roll with vendor revisions at or below the shared as-of.

  CONTROLLED(``--drop-k``)               — re-grade under ONE panel and the SAME panel with
            its first K sessions removed. Same end date, same cohort, every retained price
            byte-identical. Any movement here is the anchor re-phasing and nothing else.

The cohort is held FIXED (one ``collect_boards()`` read) in every arm, so the diff is a
pure price-panel-vintage effect: same boards, same admissions, different leading history.

Rows are compared ONLY where the episode matured in BOTH arms — a row that matured in one
and not the other moved because time passed, which is legitimate.

Run:
    python3 scripts/measure_ob_mask_track_record_blast_radius.py \
        --rev-a ca9251861b4 --rev-b 361136284f2 --drop-k 4 \
        --out reports/ob_mask_track_record_blast_radius.md
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


#: The three breadth close caches ``engine.equity_factors._closes("broad")`` concatenates.
#: `breadth` (large-cap) carries a FIXED start; midcap/smallcap are the rolling windows.
GROUPS = ("breadth", "midcap_breadth", "smallcap_breadth")

REL = "data/{grp}/_closes_cache.parquet"


def _panel_at(rev: str, workdir: Path) -> pd.DataFrame:
    """The combined close panel exactly as ``_closes('broad')`` builds it, at git rev."""
    frames = []
    for grp in GROUPS:
        rel = REL.format(grp=grp)
        blob = subprocess.run(
            ["git", "show", f"{rev}:{rel}"], cwd=ROOT, capture_output=True, check=True,
        ).stdout
        p = workdir / f"{rev}_{grp}.parquet"
        p.write_bytes(blob)
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        frames.append(df)
    out = pd.concat(frames, axis=1)
    out = out.loc[:, ~out.columns.duplicated()].sort_index()
    out.index = pd.to_datetime(out.index)
    return out


def _grade(names: pd.DataFrame, boards: list[dict], etfs: pd.DataFrame) -> dict:
    """Run the REAL ledger path (``emit_ledger``) over a given price panel."""
    from scripts.grade_us_board import emit_ledger, extend_prices_to_admitted

    names = names.copy()
    names.index = pd.to_datetime(names.index)
    names = names.sort_index()
    # Production applies this before grading; applying it in every arm keeps the yahoo-store
    # tickers identical across arms so they cannot contribute to the diff.
    names, _ = extend_prices_to_admitted(names, boards)
    return emit_ledger(boards, names, etfs)


def _rows(led: dict) -> dict[tuple[str, str], dict]:
    return {(r["t"], r["d"]): r for r in led.get("rows", [])}


def _diff(rx: dict, ry: dict) -> dict:
    """Compare episodes MATURED IN BOTH arms. A row matured in only one moved because
    time passed — that is new information and is excluded."""
    keys = [k for k in rx if k in ry and rx[k].get("m") and ry[k].get("m")]
    dy, pnl, xr, xs = [], [], [], []
    for k in keys:
        a, b = rx[k], ry[k]
        if a.get("dy") != b.get("dy"):
            dy.append({"t": k[0], "d": k[1], "from": a.get("dy"), "to": b.get("dy")})
        if (a.get("p") or 0) != (b.get("p") or 0):
            pnl.append({"t": k[0], "d": k[1], "from": a.get("p"), "to": b.get("p"),
                        "held_from": a.get("dy"), "held_to": b.get("dy"),
                        "exit_from": a.get("xr"), "exit_to": b.get("xr")})
        if a.get("xr") != b.get("xr"):
            xr.append({"t": k[0], "d": k[1], "from": a.get("xr"), "to": b.get("xr")})
        if (a.get("x") or 0) != (b.get("x") or 0):
            xs.append({"t": k[0], "d": k[1], "from": a.get("x"), "to": b.get("x")})
    deltas = sorted(abs((m["to"] or 0) - (m["from"] or 0)) for m in pnl)
    signed = [(m["to"] or 0) - (m["from"] or 0) for m in pnl]
    return {
        "n_matured_both": len(keys),
        "n_exit_bar_moved": len(dy), "n_pnl_moved": len(pnl),
        "n_exit_reason_moved": len(xr), "n_excess_moved": len(xs),
        "pnl_abs_median_pp": round(deltas[len(deltas) // 2], 2) if deltas else 0.0,
        "pnl_abs_mean_pp": round(sum(deltas) / len(deltas), 2) if deltas else 0.0,
        "pnl_abs_max_pp": round(max(deltas), 2) if deltas else 0.0,
        "pnl_signed_sum_pp": round(sum(signed), 1) if signed else 0.0,
        "exit_bar_moves": dy, "pnl_moves": pnl, "exit_reason_moves": xr,
    }


def _price_revisions(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    """How much of a NATURAL diff could be vendor revisions rather than the anchor."""
    idx = a.index.intersection(b.index)
    col = a.columns.intersection(b.columns)
    x, y = a.loc[idx, col], b.loc[idx, col]
    neq = ~((x == y) | (x.isna() & y.isna()))
    moved_start = 0
    for t in col:
        sa, sb = a[t].dropna(), b[t].dropna()
        if sa.empty or sb.empty:
            continue
        if sa.index.min() != sb.index.min():
            moved_start += 1
    return {"n_shared_dates": int(len(idx)), "n_shared_tickers": int(len(col)),
            "n_tickers_with_revised_price": int(neq.any().sum()),
            "n_revised_cells": int(neq.to_numpy().sum()),
            "n_tickers_whose_start_moved": moved_start}


def _mask_census(full: pd.DataFrame, trimmed: pd.DataFrame) -> dict:
    """Ticker-level: whose OB mask changes on dates BOTH panels cover, prices identical."""
    from scripts.grade_us_board import _ob_mask

    changed = graded = cells = 0
    for t in full.columns:
        sf, st = full[t].dropna(), trimmed[t].dropna() if t in trimmed.columns else pd.Series(dtype=float)
        if len(sf) < 200 or len(st) < 200:
            continue
        mf, mt = _ob_mask(sf), _ob_mask(st)
        if mf is None or mt is None:
            continue
        graded += 1
        idx = mf.index.intersection(mt.index)
        d = mf.loc[idx] != mt.loc[idx]
        if bool(d.any()):
            changed += 1
            cells += int(d.sum())
    return {"n_graded": graded, "n_mask_changed": changed,
            "pct_mask_changed": round(100 * changed / graded, 1) if graded else 0.0,
            "n_flipped_daily_flags": cells}


_SUM_KEYS = ("n_matured", "win_pct", "expectancy_pct", "median_pct", "profit_factor",
             "avg_win_pct", "avg_loss_pct", "median_hold", "capture",
             "ci_lo_pct", "ci_hi_pct")


def _md(res: dict) -> str:
    """The report. Numbers only — the ruling and the proposal carry the argument."""
    L: list[str] = []
    A = L.append
    A("# `_ob_mask` — US track-record blast radius")
    A("")
    A("How far `site/factordata/us_track_ledger.json` moves when only LEADING history changes.")
    A("")
    A(f"Generated by `scripts/measure_ob_mask_track_record_blast_radius.py` · "
      f"rev-a `{res['rev_a']}` · rev-b `{res['rev_b']}` · drop-k {res['drop_k']}")
    A("")
    A("Cohort held FIXED in every arm (one `collect_boards()` read), so each diff is a pure "
      "price-panel-vintage effect. Rows compared only where the episode matured in BOTH arms.")
    A("")
    A("## 1. Panels")
    A("")
    A("| arm | start | end | sessions | tickers |")
    A("|---|---|---|---:|---:|")
    for k, p in res["panels"].items():
        A(f"| {k} | {p['start']} | {p['end']} | {p['n']} | {p['cols']} |")
    A("")
    A("## 2. Movement of already-matured episodes")
    A("")
    A("| arm | matured in both | exit bar moved | P&L moved | exit reason moved | "
      "median \\|ΔP&L\\| | max \\|ΔP&L\\| |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for lab, d in res["diffs"].items():
        n = d["n_matured_both"]
        pc = f"{100 * d['n_pnl_moved'] / n:.1f}%" if n else "—"
        A(f"| {lab} | {n} | {d['n_exit_bar_moved']} | {d['n_pnl_moved']} ({pc}) | "
          f"{d['n_exit_reason_moved']} | {d['pnl_abs_median_pp']} pp | {d['pnl_abs_max_pp']} pp |")
    A("")
    A("`CONTROLLED` is the decisive arm: same end date, same cohort, every retained price "
      "byte-identical. Its movement is re-phasing alone — zero new information.")
    A("")
    A("## 3. Published headline under each panel")
    A("")
    hdr = "| metric | " + " | ".join(res["summaries"].keys()) + " |"
    A(hdr)
    A("|---" * (len(res["summaries"]) + 1) + "|")
    for k in _SUM_KEYS:
        A(f"| `{k}` | " + " | ".join(str(s.get(k)) for s in res["summaries"].values()) + " |")
    A("")
    A("`win_pct`, `expectancy_pct`, `n_matured` and the CI are the Track-record page's hero "
      "stats (`scripts/build_track_record_page.py`) and the dashboard Track-record chip "
      "(`templates/dashboard.html.j2`). They are public.")
    A("")
    A("## 4. Is the natural arm the anchor, or vendor revisions?")
    A("")
    r = res["price_revisions"]
    A(f"- shared window: {r['n_shared_dates']} dates × {r['n_shared_tickers']} tickers")
    A(f"- tickers with ANY revised price on the overlap: **{r['n_tickers_with_revised_price']}** "
      f"({r['n_revised_cells']} cells)")
    A(f"- tickers whose OWN history start moved: **{r['n_tickers_whose_start_moved']}**")
    A("")
    A("Revisions are real but a small minority; the start roll is the broad exposure. The "
      "CONTROLLED arm settles it — there, revisions are impossible by construction.")
    A("")
    A("## 5. Mask census (controlled arm — identical prices)")
    A("")
    c = res["mask_census"]
    A(f"- tickers graded: {c['n_graded']}")
    A(f"- OB mask CHANGED on shared dates: **{c['n_mask_changed']} ({c['pct_mask_changed']}%)**")
    A(f"- flipped daily flags: **{c['n_flipped_daily_flags']}**")
    A("")
    A("The complement is the large-cap `breadth` cache, whose start is fixed — it does not "
      "re-phase, which is why the share is not 100%.")
    A("")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rev-a", required=True, help="earlier collection commit")
    ap.add_argument("--rev-b", required=True, help="later collection commit")
    ap.add_argument("--drop-k", type=int, default=4,
                    help="leading sessions to drop for the CONTROLLED arm")
    ap.add_argument("--out", type=Path, default=None, help="markdown report path")
    args = ap.parse_args()

    from scripts.grade_us_board import _load_prices, collect_boards

    boards = collect_boards()
    _, etfs = _load_prices()
    print(f"[boards] {len(boards)} as_of dates "
          f"{boards[0]['as_of']}..{boards[-1]['as_of']}", flush=True)

    with tempfile.TemporaryDirectory() as td:
        wd = Path(td)
        A = _panel_at(args.rev_a, wd)
        B = _panel_at(args.rev_b, wd)
    Bp = B.iloc[args.drop_k:]

    panels = {}
    for lab, p in (("A (rev-a)", A), ("B (rev-b)", B), (f"B' (B −{args.drop_k} leading)", Bp)):
        panels[lab] = {"start": str(p.index.min().date()), "end": str(p.index.max().date()),
                       "n": int(len(p)), "cols": int(p.shape[1])}
        print(f"[panel] {lab}: {panels[lab]}", flush=True)

    ledA, ledB, ledBp = (_grade(p, boards, etfs) for p in (A, B, Bp))
    rA, rB, rBp = _rows(ledA), _rows(ledB), _rows(ledBp)

    res = {
        "rev_a": args.rev_a, "rev_b": args.rev_b, "drop_k": args.drop_k,
        "panels": panels,
        "diffs": {"NATURAL (A vs B)": _diff(rA, rB),
                  "CONTROLLED (B vs B')": _diff(rB, rBp)},
        "summaries": {"A": {k: (ledA.get("summary") or {}).get(k) for k in _SUM_KEYS},
                      "B": {k: (ledB.get("summary") or {}).get(k) for k in _SUM_KEYS},
                      "B'": {k: (ledBp.get("summary") or {}).get(k) for k in _SUM_KEYS}},
        "price_revisions": _price_revisions(A, B),
        "mask_census": _mask_census(B, Bp),
    }

    for lab, d in res["diffs"].items():
        print(f"[{lab}] matured_both={d['n_matured_both']} pnl_moved={d['n_pnl_moved']} "
              f"exit_bar_moved={d['n_exit_bar_moved']} max|Δ|={d['pnl_abs_max_pp']}pp", flush=True)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(_md(res))
        args.out.with_suffix(".json").write_text(json.dumps(res, indent=1, default=str))
        print(f"[wrote] {args.out} + {args.out.with_suffix('.json')}", flush=True)
    else:
        print(_md(res))


if __name__ == "__main__":
    # Script-only: silencing the process-global warnings filter at import time
    # mutes it for every importer, which `tests/test_no_module_level_logging_disable`
    # ratchets against. Scoped to the CLI entrypoint (the walk_forward.py idiom the
    # guard names), the noise suppression is kept for humans running the measurement
    # while importers get their own filter state back.
    warnings.filterwarnings("ignore")
    main()
