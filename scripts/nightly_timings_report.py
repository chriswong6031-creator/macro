"""Trend reader for the nightly timings ledger (masterplan W2's "one reader script").

Reads data/ops/nightly_timings/<job>.jsonl (written nightly by
scripts/nightly_timings.py via each daily.yml job's final step) and prints a
per-job budget table over the last N nights: median/max elapsed, percent of the
job's timeout-minutes cap, and how many nights crossed the 85% tripwire —
so caps get re-budgeted from trend data BEFORE a kill night, not after.

``--sources`` reads the W-L1 per-source attribution block that
scripts/nightly_timings.py copies out of data/run_status.json: which collectors
actually spend the ~130m `collectors` band, and how much of that band no
collector explains. That residue is the migration argument — you cannot pick the
first source to move off the nightly path from a monolith's total.

Usage:  python3 scripts/nightly_timings_report.py [--nights 14] [--bands]
                                                  [--sources [N]] [--job collect]
Stdlib-only; read-only; safe to run anywhere.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

DEFAULT_LEDGER_DIR = Path("data/ops/nightly_timings")
WARN_PCT = 85.0
WATCH_PCT = 70.0  # median above this = creep worth re-budgeting proactively


def load_rows(ledger_dir: Path) -> dict[str, list[dict]]:
    jobs: dict[str, list[dict]] = {}
    for path in sorted(ledger_dir.glob("*.jsonl")):
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("elapsed_minutes") is not None:
                rows.append(row)
        if rows:
            jobs[path.stem] = rows
    return jobs


def _nights(n: int) -> str:
    return f"{n} night" if n == 1 else f"{n} nights"


def source_lines(rows: list[dict], top: int) -> list[str]:
    """Per-source attribution across ``rows`` (medians, so one odd night cannot
    nominate a migration target on its own).

    Everything here is a report of measurements: nothing ranks, gates or sizes a
    signal, and a source that ran untimed is listed as ``null``, never as 0 —
    a zero would sort an unknown to the fastest end of the very table used to
    choose what leaves the nightly path.
    """
    out: list[str] = []
    per_band: dict[str, dict] = {}
    band_order: list[str] = []
    for row in rows:
        for band in (row.get("source_attribution") or {}).get("bands") or []:
            name = band.get("band")
            if name not in per_band:
                per_band[name] = {"band": [], "attributed": [], "residue": [],
                                  "sources": {}, "nulls": {}}
                band_order.append(name)
            acc = per_band[name]
            acc["band"].append(float(band.get("band_sec") or 0))
            acc["attributed"].append(float(band.get("attributed_sec") or 0))
            acc["residue"].append(float(band.get("residue_sec") or 0))
            for src, sec in (band.get("sources") or {}).items():
                if sec is None:
                    acc["nulls"][src] = acc["nulls"].get(src, 0) + 1
                else:
                    acc["sources"].setdefault(src, []).append(float(sec))

    for name in band_order:
        acc = per_band[name]
        band_med = statistics.median(acc["band"])
        attr_med = statistics.median(acc["attributed"])
        res_med = statistics.median(acc["residue"])
        share = (100.0 * res_med / band_med) if band_med else 0.0
        out.append(f"    attribution · {name}: band median {band_med / 60:.1f}m = "
                   f"attributed {attr_med / 60:.1f}m + residue {res_med / 60:.1f}m "
                   f"({share:.0f}% of the band, {_nights(len(acc['band']))})")
        ranked = sorted(((s, statistics.median(v), len(v)) for s, v in acc["sources"].items()),
                        key=lambda svn: (-svn[1], svn[0]))
        for src, med, n in ranked[:top]:
            out.append(f"        {src:<32} {med / 60:>6.1f}m  ({med:>7.1f}s, {_nights(n)})")
        if len(ranked) > top:
            out.append(f"        … {len(ranked) - top} more source(s) — full list in the ledger row")
        for src, n in sorted(acc["nulls"].items()):
            out.append(f"        {src:<32} {'null':>6}   "
                       f"(ran, NO elapsed measurement, {_nights(n)})")
    return out


def report(ledger_dir: Path, nights: int, show_bands: bool,
           show_sources: int = 0, only_job: str | None = None) -> list[str]:
    jobs = load_rows(ledger_dir)
    if only_job:
        jobs = {k: v for k, v in jobs.items() if k == only_job}
    out: list[str] = []
    if not jobs:
        out.append(f"no timings rows under {ledger_dir} — has the nightly run since W2 shipped?")
        return out

    header = (f"{'job':<24} {'cap':>5} {'nights':>6} {'median':>8} {'max':>8} "
              f"{'med%':>5} {'max%':>5} {'>85%':>5}  flag")
    out.append(header)
    out.append("-" * len(header))
    for job, rows in sorted(jobs.items()):
        recent = sorted(rows, key=lambda r: (r.get("date", ""), r.get("end", "")))[-nights:]
        elapsed = [float(r["elapsed_minutes"]) for r in recent]
        cap = float(recent[-1].get("cap_minutes") or 0)
        med = statistics.median(elapsed)
        mx = max(elapsed)
        med_pct = 100.0 * med / cap if cap else 0.0
        max_pct = 100.0 * mx / cap if cap else 0.0
        breaches = sum(1 for e in elapsed if cap and 100.0 * e / cap > WARN_PCT)
        flag = ""
        if breaches:
            flag = "TRIPWIRE — re-budget or trim NOW"
        elif med_pct > WATCH_PCT:
            flag = "creep watch (median >70% of cap)"
        out.append(f"{job:<24} {cap:>4.0f}m {len(recent):>6} {med:>7.1f}m {mx:>7.1f}m "
                   f"{med_pct:>4.0f}% {max_pct:>4.0f}% {breaches:>5}  {flag}")

        if show_bands:
            band_vals: dict[str, list[float]] = {}
            band_order: list[str] = []
            for r in recent:
                for b in r.get("bands") or []:
                    if b["band"] not in band_vals:
                        band_vals[b["band"]] = []
                        band_order.append(b["band"])
                    band_vals[b["band"]].append(float(b["seconds"]) / 60.0)
            for band in band_order:
                vals = band_vals[band]
                out.append(f"    · {band:<20} median {statistics.median(vals):>6.1f}m  "
                           f"max {max(vals):>6.1f}m  ({len(vals)} nights)")

        if show_sources:
            out.extend(source_lines(recent, show_sources))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledger-dir", type=Path, default=DEFAULT_LEDGER_DIR)
    ap.add_argument("--nights", type=int, default=14)
    ap.add_argument("--bands", action="store_true", help="also print per-band medians")
    ap.add_argument("--sources", type=int, nargs="?", const=15, default=0, metavar="N",
                    help="also print the W-L1 per-source attribution (top N by median "
                         "elapsed, plus the unattributed residue and any untimed sources)")
    ap.add_argument("--job", default=None, help="restrict the report to one job (e.g. collect)")
    args = ap.parse_args(argv)
    for line in report(args.ledger_dir, args.nights, args.bands,
                       show_sources=args.sources, only_job=args.job):
        print(line, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
