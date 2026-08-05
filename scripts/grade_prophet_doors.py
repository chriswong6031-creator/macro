"""Prophet W3 shadow doors — forward grader (policy-free, fixed-horizon marks).

Grades matured rows of `data/prophet_doors/flags.jsonl` at **H=10 and H=21 sessions** and
writes one grade row per (flag, horizon) to `data/prophet_doors/grades.jsonl`.

RULER — REUSED, NOT FORKED (one-grader law §1.2)
------------------------------------------------
Every return in this file comes from `engine.grading.forward_metrics`, the same function
`scripts/grade_us_board.py` grades the live US board with:

  * **next-bar fill** — entry is the close of the bar STRICTLY AFTER the flag bar, so a flag
    computed on tonight's close is filled at tomorrow's close. No same-bar entry anywhere.
  * **positional horizons** — H is an integer offset on the price index, and those parquets
    hold trading days only, so H=10 is ten SESSIONS, never ten calendar days.
  * **excess vs SPY** = ``fwd_ret_H(name) - fwd_ret_H(SPY)``, with SPY reindexed onto the
    name's own calendar and forward-filled before it is graded — byte-identical to
    grade_us_board's ``excess_spy`` construction (that file's lines 556-663).

POLICY-FREE
-----------
Fixed-horizon marks ONLY. No stops, no exits, no early-exit series, no hold rules, no
sizing. A door is being measured as an ORIGINATION construction; layering an exit policy on
top would grade the policy instead. (`engine.track_scoring.score_episode` is the sibling
machinery that DOES carry stops/exits — deliberately not used here for that reason.)

ONE-GRADER LAW
--------------
A graded (flag_date, door, ticker, horizon) row is FROZEN and never regraded. Re-runs only
add newly-matured rows, so the file is idempotent per as_of.

NIGHTLY-ONLY: forward advance under `--nightly`, additionally gated by
`engine.ledger_lane.nightly_advance_enabled` (COLLECT_LANE=nightly).

ZERO AUTHORITY: outcomes here confer no rank/gate/size/board rights on any door. Promotion
requires the pre-registered gate in `research/PROPHET_DOORS_PREREG.md` §4, and a PASS there
buys only an operator-ratified REVIEW.

Run (nightly / DAG):  python -m scripts.grade_prophet_doors --nightly
Run (safe preview):   python -m scripts.grade_prophet_doors --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import prophet_doors as pd_doors  # noqa: E402
from engine.grading import forward_metrics  # noqa: E402
from engine.ledger_lane import nightly_advance_enabled as _ledger_advance_enabled  # noqa: E402

log = logging.getLogger("grade_prophet_doors")

GRADE_SCHEMA = "prophet_doors_grade/v1"
HORIZONS = (10, 21)
BENCH = "SPY"


def grades_path(root: Path | None = None) -> Path:
    return pd_doors.ledger_dir(root) / "grades.jsonl"


def load_grades(root: Path | None = None) -> list[dict]:
    """Every grade row. [] when the file is absent."""
    p = grades_path(root)
    if not p.exists():
        return []
    out: list[dict] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError as e:
        log.warning("grade_prophet_doors: grades read failed (%s)", e)
    return out


def append_grades(rows: list[dict], root: Path | None = None) -> int:
    """Append grade rows. NIGHTLY-ONLY — off-lane this is a no-op returning 0."""
    if not _ledger_advance_enabled():
        log.debug("grade_prophet_doors.append_grades: skipped (COLLECT_LANE != nightly)")
        return 0
    if not rows:
        return 0
    p = grades_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    return len(rows)


def load_bench(root: Path | None = None) -> pd.Series | None:
    """SPY dividend-adjusted closes from `data/yahoo/SPY.parquet` — the same per-ticker cache
    and the same benchmark `grade_us_board` uses (`BENCH = "SPY"`)."""
    p = Path(root or ROOT) / "data" / "yahoo" / f"{BENCH}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        s = df["close"] if "close" in df.columns else df.iloc[:, 0]
        s.index = pd.to_datetime(s.index)
        return s.sort_index().dropna()
    except Exception as e:  # noqa: BLE001
        log.warning("grade_prophet_doors: bench read failed (%s)", e)
        return None


def grade_flag(close: pd.Series, bench: pd.Series | None, flag_date: Any,
               horizons: tuple[int, ...] = HORIZONS) -> dict[int, dict]:
    """{H: mark} for every horizon that has MATURED for this flag.

    A horizon is matured only when the full forward window exists in the cache AND the
    horizon bar is at or before the last bar we hold — an unmatured H is simply absent from
    the result, so it is graded on a later night instead of being marked short.
    """
    out: dict[int, dict] = {}
    c = close.dropna()
    if c.empty:
        return out
    if not isinstance(c.index, pd.DatetimeIndex):
        c = c.copy()
        c.index = pd.to_datetime(c.index)

    fwd = forward_metrics(c, flag_date, horizons=horizons)
    if fwd.get("entry_price") is None:
        return out

    # Benchmark on the NAME's calendar (grade_us_board's `spy_al` construction), then graded
    # through the identical ruler so the two legs of the excess share a fill convention.
    b_al = bench.reindex(c.index).ffill() if bench is not None else None
    b_fwd = forward_metrics(b_al, flag_date, horizons=horizons) if b_al is not None else {}

    last_bar = c.index[-1]
    fill_pos = c.index.searchsorted(pd.Timestamp(fwd["fill_date"]), side="left")
    for h in horizons:
        r = fwd.get(f"fwd_ret_{h}")
        if r is None:
            continue
        if fill_pos + h >= len(c) or c.index[fill_pos + h] > last_bar:
            continue
        b_ret = b_fwd.get(f"fwd_ret_{h}")
        out[h] = {
            "horizon": h,
            "entry_price": round(float(fwd["entry_price"]), 6),
            "fill_date": fwd["fill_date"],
            "mark_date": str(c.index[fill_pos + h].date()),
            "fwd_ret": round(float(r), 6),
            "bench": BENCH,
            "bench_ret": (round(float(b_ret), 6) if b_ret is not None else None),
            "excess_spy": (round(float(r) - float(b_ret), 6) if b_ret is not None else None),
            "fwd_mfe": (round(float(fwd[f"fwd_mfe_{h}"]), 6)
                        if fwd.get(f"fwd_mfe_{h}") is not None else None),
            "fwd_mdd": (round(float(fwd[f"fwd_mdd_{h}"]), 6)
                        if fwd.get(f"fwd_mdd_{h}") is not None else None),
        }
    return out


def run(root: Path | None = None, *, dry_run: bool = False,
        universe: pd.DataFrame | None = None) -> dict:
    """Grade every newly-matured (flag, horizon) pair. Returns the run document."""
    root = Path(root or ROOT)
    flags = pd_doors.load_flags(root)
    doc: dict[str, Any] = {
        "schema": GRADE_SCHEMA, "asof": None, "n_flags": len(flags),
        "new_grades": 0, "appended": 0, "dry_run": bool(dry_run),
        "by_door": {d: 0 for d in pd_doors.DOORS}, "rows": [],
        "skipped_no_price": 0, "pending": 0,
    }
    if not flags:
        doc["note"] = "no flags accrued yet — the ledger starts at merge (prospective only)"
        return doc

    px = pd_doors.load_universe(root) if universe is None else universe
    if px is None or px.empty:
        print("::warning title=prophet_doors_grade::universe cache empty; nothing graded",
              flush=True)
        return doc
    doc["asof"] = str(px.index[-1].date())
    bench = load_bench(root)
    if bench is None:
        print("::warning title=prophet_doors_grade::SPY cache missing; excess columns will be "
              "null (absolute marks still graded)", flush=True)

    # One-grader law: a (flag_date, door, ticker, horizon) already graded is frozen.
    done = {(g.get("date"), g.get("door"), g.get("ticker"), g.get("horizon"))
            for g in load_grades(root)}

    new_rows: list[dict] = []
    for fl in flags:
        tk, door, d0 = fl.get("ticker"), fl.get("door"), fl.get("date")
        if not (tk and door and d0):
            continue
        if all((d0, door, tk, h) in done for h in HORIZONS):
            continue
        if tk not in px.columns:
            doc["skipped_no_price"] += 1
            continue
        marks = grade_flag(px[tk], bench, d0)
        if not marks:
            doc["pending"] += 1
            continue
        for h, m in sorted(marks.items()):
            if (d0, door, tk, h) in done:
                continue
            new_rows.append({"schema": GRADE_SCHEMA, "date": d0, "door": door,
                             "ticker": tk, **m})
            doc["by_door"][door] = doc["by_door"].get(door, 0) + 1

    new_rows.sort(key=lambda r: (r["date"], r["door"], r["ticker"], r["horizon"]))
    doc["new_grades"] = len(new_rows)
    doc["rows"] = new_rows
    if not dry_run:
        doc["appended"] = append_grades(new_rows, root)
    log.info("grade_prophet_doors: flags=%d new_grades=%d pending=%d no_price=%d",
             len(flags), len(new_rows), doc["pending"], doc["skipped_no_price"])
    return doc


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nightly", action="store_true",
                    help="forward-advance the grade ledger (the SOLE advancer; DAG entry point)")
    ap.add_argument("--dry-run", action="store_true",
                    help="grade and print; writes nothing")
    ap.add_argument("--json", action="store_true", help="dump the run document as JSON")
    args = ap.parse_args()

    doc = run(dry_run=bool(args.dry_run or not args.nightly))
    if args.json:
        print(json.dumps(doc, indent=2, ensure_ascii=False, default=str))
        return
    print(f"prophet_doors grades asof={doc.get('asof')} flags={doc['n_flags']} "
          f"new={doc['new_grades']} pending={doc['pending']} "
          f"no_price={doc['skipped_no_price']} appended={doc['appended']} "
          f"dry_run={doc['dry_run']}")
    if doc.get("note"):
        print(f"  {doc['note']}")
    for r in doc["rows"][:50]:
        print(f"    {r['date']} door {r['door']} {r['ticker']:<6} H={r['horizon']:<3} "
              f"ret={r['fwd_ret']:+.4f} spy={r['bench_ret']} excess={r['excess_spy']}")


if __name__ == "__main__":
    main()
